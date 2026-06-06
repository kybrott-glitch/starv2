"""
child_runner.py
Manages dynamically spawned child bot instances.
Each child bot runs in its own asyncio task with its own Application.
"""

import asyncio
import json
import logging
import math
from telegram import Update, LabeledPrice
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    ContextTypes,
    filters,
)
from config import PLATFORM_FEE_PERCENT, FATHER_BOT_TOKEN
from db import db

logger = logging.getLogger(__name__)

# Registry: bot_id -> {"app": Application, "task": asyncio.Task}
_running_bots: dict[str, dict] = {}


def _calc_fee(stars: int) -> int:
    """Calculate platform fee, minimum 1 star."""
    return max(1, math.ceil(stars * PLATFORM_FEE_PERCENT / 100))


def _build_child_app(token: str, bot_id: str, owner_id: int) -> Application:
    """Build a fully configured child bot Application."""

    app = Application.builder().token(token).build()

    # ── /start ────────────────────────────────────────────────────────────────
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        bot_info = db.get_bot_by_id(bot_id)
        name = bot_info["display_name"] if bot_info else "Payment Bot"
        await update.message.reply_text(
            f"👋 Welcome to *{name}*!\n\n"
            f"Use the payment link shared by the admin to pay with ⭐ Stars.",
            parse_mode="Markdown"
        )

    # ── /createlink ───────────────────────────────────────────────────────────
    async def create_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id != owner_id:
            return await update.message.reply_text("❌ Only the bot owner can do this.")

        args = context.args
        if len(args) < 2:
            return await update.message.reply_text(
                "Usage: `/createlink <stars> <label>`\nExample: `/createlink 50 VIP Access`",
                parse_mode="Markdown"
            )

        try:
            amount = int(args[0])
            if amount < 1:
                raise ValueError
        except ValueError:
            return await update.message.reply_text("❌ Stars amount must be a positive integer.")

        label = " ".join(args[1:])
        fee = _calc_fee(amount)
        net = amount - fee

        link_id = db.create_link(
            child_bot_id=bot_id,
            owner_id=owner_id,
            amount=amount,
            label=label
        )

        try:
            invoice_url = await context.bot.create_invoice_link(
                title=label,
                description=f"{amount} Stars — {label}",
                payload=json.dumps({"link_id": link_id, "bot_id": bot_id, "owner_id": owner_id}),
                provider_token="",
                currency="XTR",
                prices=[LabeledPrice(label=label, amount=amount)],
            )
        except Exception as e:
            db.delete_link(link_id=link_id, owner_id=owner_id)
            return await update.message.reply_text(f"❌ Failed to generate link: {e}")

        db.save_invoice_url(link_id=link_id, url=invoice_url)

        await update.message.reply_text(
            f"✅ Payment link created!\n\n"
            f"🆔 ID: {link_id}\n"
            f"⭐ Stars: {amount}\n"
            f"🏷 Label: {label}\n"
            f"📊 You receive: {net} stars (after {PLATFORM_FEE_PERCENT}% fee)\n\n"
            f"🔗 Share this link:\n{invoice_url}\n\n"
            f"Set a custom reply:\n/setmessage {link_id} Your message here"
        )

    # ── /setmessage ───────────────────────────────────────────────────────────
    async def set_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id != owner_id:
            return await update.message.reply_text("❌ Only the bot owner can do this.")

        args = context.args
        if len(args) < 2:
            return await update.message.reply_text(
                "Usage: `/setmessage <link_id> <message>`",
                parse_mode="Markdown"
            )

        link_id = args[0]
        message = " ".join(args[1:])
        success = db.set_custom_message(link_id=link_id, owner_id=owner_id, message=message)

        if success:
            await update.message.reply_text(f"✅ Reply message set for link {link_id}:\n\n{message}")
        else:
            await update.message.reply_text("❌ Link not found or not yours.")

    # ── /links ────────────────────────────────────────────────────────────────
    async def list_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id != owner_id:
            return

        links = db.get_bot_links(child_bot_id=bot_id, owner_id=owner_id)
        if not links:
            return await update.message.reply_text("No links yet. Use /createlink to create one.")

        text = "📋 Your Payment Links\n\n"
        for link in links:
            fee = _calc_fee(link["amount"])
            net = link["amount"] - fee
            url = link.get("invoice_url") or "(generating...)"
            msg = (link["message"][:30] + "...") if link["message"] and len(link["message"]) > 30 else (link["message"] or "(not set)")
            text += (
                f"🆔 {link['id']} — ⭐ {link['amount']} (you get {net}) — {link['label']}\n"
                f"   🔗 {url}\n"
                f"   💬 Reply: {msg}\n"
                f"   💰 Paid: {link['payment_count']} time(s)\n\n"
            )

        await update.message.reply_text(text)

    # ── /stats ────────────────────────────────────────────────────────────────
    async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id != owner_id:
            return

        s = db.get_owner_stats(owner_id)
        fee_pct = PLATFORM_FEE_PERCENT
        await update.message.reply_text(
            f"📊 Your Stats\n\n"
            f"🔗 Total links: {s.get('total_links', 0)}\n"
            f"💰 Total payments: {s.get('total_payments', 0)}\n"
            f"⭐ Total stars received: {s.get('total_stars', 0)}\n"
            f"📊 Platform fee paid ({fee_pct}%): {s.get('total_fees', 0)} stars"
        )

    # ── /deletelink ───────────────────────────────────────────────────────────
    async def delete_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id != owner_id:
            return

        if not context.args:
            return await update.message.reply_text("Usage: /deletelink <link_id>")

        success = db.delete_link(link_id=context.args[0], owner_id=owner_id)
        await update.message.reply_text(
            f"🗑 Link deleted." if success else "❌ Link not found."
        )

    # ── pre_checkout ──────────────────────────────────────────────────────────
    async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.pre_checkout_query.answer(ok=True)

    # ── successful_payment ────────────────────────────────────────────────────
    async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
        payment = update.message.successful_payment
        buyer = update.effective_user

        try:
            payload = json.loads(payment.invoice_payload)
            link_id = payload["link_id"]
        except Exception:
            await update.message.reply_text("✅ Payment received! Thank you! ⭐")
            return

        stars = payment.total_amount
        fee_stars = _calc_fee(stars)

        # Record in DB
        payment_id = db.record_payment(
            link_id=link_id,
            child_bot_id=bot_id,
            owner_id=owner_id,
            user_id=buyer.id,
            username=buyer.username or "",
            stars=stars,
            fee_stars=fee_stars,
        )

        # Send custom message to buyer
        link = db.get_link(link_id)
        custom_msg = link["message"] if link and link["message"] else None
        await update.message.reply_text(
            custom_msg if custom_msg else f"✅ Payment received! Thank you, {buyer.first_name}! ⭐"
        )

        # Notify owner
        try:
            await context.bot.send_message(
                chat_id=owner_id,
                text=(
                    f"💰 New payment!\n\n"
                    f"👤 {buyer.first_name}" + (f" (@{buyer.username})" if buyer.username else "") + "\n"
                    f"⭐ Stars: {stars}\n"
                    f"📊 Platform fee: {fee_stars} stars ({PLATFORM_FEE_PERCENT}%)\n"
                    f"💵 You received: {stars - fee_stars} stars net"
                )
            )
        except Exception as e:
            logger.warning(f"Could not notify owner {owner_id}: {e}")

        # Send fee invoice to owner via FATHER BOT
        asyncio.create_task(
            _charge_platform_fee(
                owner_id=owner_id,
                fee_stars=fee_stars,
                payment_id=payment_id,
                label=link["label"] if link else "Payment",
                buyer_name=buyer.first_name,
            )
        )

    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("createlink", create_link))
    app.add_handler(CommandHandler("setmessage", set_message))
    app.add_handler(CommandHandler("links", list_links))
    app.add_handler(CommandHandler("deletelink", delete_link))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    return app


async def _charge_platform_fee(owner_id: int, fee_stars: int, payment_id: int,
                                 label: str, buyer_name: str):
    """Send a Stars fee invoice from the father bot to the child bot owner."""
    try:
        from telegram import Bot
        father_bot = Bot(token=FATHER_BOT_TOKEN)

        invoice_url = await father_bot.create_invoice_link(
            title=f"Platform Fee — {label}",
            description=f"7% fee for payment from {buyer_name} ({fee_stars} stars)",
            payload=json.dumps({"type": "platform_fee", "payment_id": payment_id}),
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="Platform Fee (7%)", amount=fee_stars)],
        )

        db.record_fee_invoice(
            payment_id=payment_id,
            owner_id=owner_id,
            fee_stars=fee_stars,
            invoice_url=invoice_url,
        )

        await father_bot.send_message(
            chat_id=owner_id,
            text=(
                f"📊 *Platform Fee Invoice*\n\n"
                f"A payment was received on your bot.\n"
                f"Please pay the {PLATFORM_FEE_PERCENT}% platform fee:\n\n"
                f"⭐ Fee: *{fee_stars} Stars*\n\n"
                f"👇 Tap to pay:"
            ),
            parse_mode="Markdown"
        )

        await father_bot.send_invoice(
            chat_id=owner_id,
            title=f"Platform Fee — {label}",
            description=f"7% platform fee ({fee_stars} stars)",
            payload=json.dumps({"type": "platform_fee", "payment_id": payment_id}),
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="Platform Fee (7%)", amount=fee_stars)],
        )

        await father_bot.close()

    except Exception as e:
        logger.error(f"Failed to send fee invoice to owner {owner_id}: {e}")


# ── Public API ────────────────────────────────────────────────────────────────

async def start_child_bot(token: str, bot_id: str, owner_id: int):
    """Start a child bot as a background asyncio task."""
    if bot_id in _running_bots:
        logger.info(f"Bot {bot_id} already running.")
        return

    try:
        app = _build_child_app(token=token, bot_id=bot_id, owner_id=owner_id)
        await app.initialize()
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

        task = asyncio.create_task(_keep_running(app, bot_id))
        _running_bots[bot_id] = {"app": app, "task": task}
        logger.info(f"Child bot {bot_id} started.")
    except Exception as e:
        logger.error(f"Failed to start child bot {bot_id}: {e}")
        raise


async def stop_child_bot(bot_id: str):
    """Stop a running child bot."""
    entry = _running_bots.pop(bot_id, None)
    if not entry:
        return
    try:
        app = entry["app"]
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        entry["task"].cancel()
        logger.info(f"Child bot {bot_id} stopped.")
    except Exception as e:
        logger.error(f"Error stopping child bot {bot_id}: {e}")


async def _keep_running(app: Application, bot_id: str):
    """Keep the task alive while the bot is running."""
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass


def is_running(bot_id: str) -> bool:
    return bot_id in _running_bots


async def start_all_bots():
    """Called on father bot startup — restore all previously registered bots."""
    bots = db.get_all_active_bots()
    logger.info(f"Restoring {len(bots)} child bot(s)...")
    for bot in bots:
        try:
            await start_child_bot(
                token=bot["token"],
                bot_id=bot["id"],
                owner_id=bot["owner_id"]
            )
        except Exception as e:
            logger.error(f"Could not restore bot {bot['id']}: {e}")
