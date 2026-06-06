import os

# ── Father bot (your bot) ─────────────────────────────────────────────────────
FATHER_BOT_TOKEN = os.getenv("FATHER_BOT_TOKEN", "YOUR_FATHER_BOT_TOKEN")

# Your Telegram user ID — platform owner
PLATFORM_OWNER_IDS: list[int] = [
    int(x.strip()) for x in os.getenv("PLATFORM_OWNER_IDS", "YOUR_TELEGRAM_ID").split(",")
    if x.strip().isdigit()
]

# Platform fee percentage (7%)
PLATFORM_FEE_PERCENT = 7
