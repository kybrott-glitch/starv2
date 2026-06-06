"""
father_bot.py
The main platform bot. Users register their bots here,
manage them, and the platform collects 7% fees automatically.
"""

import asyncio
import json
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from config import FATHER_BOT_TOKEN, PLATFORM_OWNER_IDS, PLATFORM_FEE_PERCENT
from db import db
from child_runner import start_child_bot, stop_child_bot, is_running, start_all_bots

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

AWAITING_TOKEN = 1


# ─── /start ───────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_owner = user.id in PLATFORM_OWNER_IDS

    owner_section = ""
    if is_owner:
        owner_section = (
            "\n\n👑 *Platform Owner Commands:*\n"
            "• /platformstats — total platform stats\n"
        )

    await update.message.reply_text(
        f"🤖 *Stars Payment Platform*\n\n"
        f"Connect your Telegram bot and accept ⭐ Stars payments with custom links.\n"
        f"Platform fee: *{PLATFORM_FEE_PERCENT}%* per transaction (auto-charged).\n\n"
        f"*Commands:*\n"
        f"• /addbot — connect your bot token\n"
        f"• /mybots — list your connected bots\n"
        f"• /removebot `<bot_id>` — disconnect a bot\n"
        f"• /use `<bot_id>` — manage a bot's payment links\n"
        f"• /stats `<bot_id>` — view earnings for a bot"
        f"{owner_section}",
        parse_mode="Markdown"
    )


# ─── Add bot flow ─────────────────────────────────────────────────────────────

async def add_bot_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔑 Send me your bot token.\n\n"
        "_Get it from @BotFather → /mybots → your bot → API Token_\n\n"
        "Send /cancel to abort.",
        parse_mode="Markdown"
    )
    return AWAITING_TOKEN


async def add_bot_receive_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    token = update.message.text.strip()

    # Basic token format check
    if ":" not in token or len(token) < 30:
        await update.message.reply_text("❌ That doesn't look like a valid bot token. Try again or /cancel.")
        return AWAITING_TOKEN

    if db.token_exists(token):
        await update.message.reply_text("❌ This token is already registered on the platform.")
        return ConversationHandler.END

    # Validate token by fetching bot info
    try:
        from telegram import Bot
        temp_bot = Bot(token=token)
        bot_info = await temp_bot.get_me()
        await temp_bot.close()
    except Exception as e:
        await update.message.reply_text(f"❌ Invalid token or bot unreachable: {e}")
        return AWAITING_TOKEN

    username = bot_info.username or ""
    display_name = bot_info.first_name or username

    # Register in DB
    bot_id = db.register_bot(
        owner_id=user.id,
        token=token,
        username=username,
        display_name=display_name
    )

    # Start the child bot
    msg = await update.message.reply_text(f"⏳ Starting @{username}...")
    try:
        await start_child_bot(token=token, bot_id=bot_id, owner_id=user.id)
        await msg.edit_text(
            f"✅ *Bot connected and running!*\n\n"
            f"🤖 @{username} ({display_name})\n"
            f"🆔 Bot ID: `{bot_id}`\n\n"
            f"Now go to *@{username}* and use:\n"
            f"`/createlink 50 VIP Access` — to create a payment link\n\n"
            f"Platform fee: {PLATFORM_FEE_PERCENT}% per payment (auto-charged to you via this bot).",
            parse_mode="Markdown"
        )
    except Exception as e:
        db.deactivate_bot(bot_id=bot_id, owner_id=user.id)
        await msg.edit_text(f"❌ Failed to start bot: {e}\nPlease check the token and try again.")

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


# ─── /mybots ─────────────────────────────────────────────────────────────────

async def my_bots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    bots = db.get_owner_bots(user.id)

    if not bots:
        return await update.message.reply_text(
            "You have no bots connected yet. Use /addbot to get started."
        )

    text = "🤖 *Your Connected Bots*\n\n"
    for bot in bots:
        status = "🟢 Running" if is_running(bot["id"]) else "🔴 Stopped"
        text += (
            f"*@{bot['username']}* ({bot['display_name']})\n"
            f"🆔 ID: `{bot['id']}`\n"
            f"Status: {status}\n\n"
        )

    text += "_Use /use `<bot_id>` to manage a bot's links._"
    await update.message.reply_text(text, parse_mode="Markdown")


# ─── /use <bot_id> ────────────────────────────────────────────────────────────

async def use_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        return await update.message.reply_text("Usage: `/use <bot_id>`", parse_mode="Markdown")

    bot_id = context.args[0].upper()
    bot = db.get_bot_by_id(bot_id)

    if not bot or bot["owner_id"] != user.id:
        return await update.message.reply_text("❌ Bot not found or not yours.")

    status = "🟢 Running" if is_running(bot_id) else "🔴 Stopped"
    links = db.get_bot_links(child_bot_id=bot_id, owner_id=user.id)
    link_count = len(links)

    await update.message.reply_text(
        f"🤖 *@{bot['username']}* — `{bot_id}`\n"
        f"Status: {status}\n"
        f"Links: {link_count}\n\n"
        f"Go to @{bot['username']} and use:\n"
        f"• `/createlink <stars> <label>` — create payment link\n"
        f"• `/setmessage <link_id> <msg>` — set reply message\n"
        f"• `/links` — see all links\n"
        f"• `/stats` — earnings",
        parse_mode="Markdown"
    )


# ─── /removebot <bot_id> ──────────────────────────────────────────────────────

async def remove_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        return await update.message.reply_text("Usage: `/removebot <bot_id>`", parse_mode="Markdown")

    bot_id = context.args[0].upper()
    bot = db.get_bot_by_id(bot_id)

    if not bot or bot["owner_id"] != user.id:
        return await update.message.reply_text("❌ Bot not found or not yours.")

    await stop_child_bot(bot_id)
    db.deactivate_bot(bot_id=bot_id, owner_id=user.id)

    await update.message.reply_text(
        f"✅ @{bot['username']} has been disconnected and stopped."
    )


# ─── /stats <bot_id> ─────────────────────────────────────────────────────────

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        # Show aggregate stats across all bots
        s = db.get_owner_stats(user.id)
        return await update.message.reply_text(
            f"📊 *Your Total Stats*\n\n"
            f"🔗 Links created: {s.get('total_links', 0)}\n"
            f"💰 Payments received: {s.get('total_payments', 0)}\n"
            f"⭐ Stars received: {s.get('total_stars', 0)}\n"
            f"📊 Platform fees paid: {s.get('total_fees', 0)} stars",
            parse_mode="Markdown"
        )

    bot_id = context.args[0].upper()
    bot = db.get_bot_by_id(bot_id)
    if not bot or bot["owner_id"] != user.id:
        return await update.message.reply_text("❌ Bot not found or not yours.")

    s = db.get_owner_stats(user.id)
    await update.message.reply_text(
        f"📊 *Stats for @{bot['username']}*\n\n"
        f"🔗 Links: {s.get('total_links', 0)}\n"
        f"💰 Payments: {s.get('total_payments', 0)}\n"
        f"⭐ Stars received: {s.get('total_stars', 0)}\n"
        f"📊 Fees paid: {s.get('total_fees', 0)} stars",
        parse_mode="Markdown"
    )


# ─── /platformstats (owner only) ─────────────────────────────────────────────

async def platform_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in PLATFORM_OWNER_IDS:
        return

    s = db.get_platform_stats()
    await update.message.reply_text(
        f"👑 *Platform Stats*\n\n"
        f"🤖 Total bots: {s.get('total_bots', 0)}\n"
        f"💰 Total payments: {s.get('total_payments', 0)}\n"
        f"⭐ Total stars processed: {s.get('total_stars', 0)}\n"
        f"📊 Total fees collected: {s.get('total_fees', 0)} stars ({PLATFORM_FEE_PERCENT}%)",
        parse_mode="Markdown"
    )


# ─── Fee payment handler (owner pays 7% back to platform) ────────────────────

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    try:
        payload = json.loads(payment.invoice_payload)
        if payload.get("type") == "platform_fee":
            await update.message.reply_text(
                f"✅ Platform fee of {payment.total_amount} ⭐ received. Thank you!"
            )
    except Exception:
        pass


# ─── Main ─────────────────────────────────────────────────────────────────────

async def post_init(app: Application):
    """Restore all child bots on startup."""
    await start_all_bots()


def main():
    app = (
        Application.builder()
        .token(FATHER_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Conversation handler for /addbot
    conv = ConversationHandler(
        entry_points=[CommandHandler("addbot", add_bot_start)],
        states={
            AWAITING_TOKEN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_bot_receive_token)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.add_handler(CommandHandler("mybots", my_bots))
    app.add_handler(CommandHandler("use", use_bot))
    app.add_handler(CommandHandler("removebot", remove_bot))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("platformstats", platform_stats))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    logger.info("Father bot started.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
