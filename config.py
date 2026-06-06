import os

# ── Father bot (your bot) ─────────────────────────────────────────────────────
FATHER_BOT_TOKEN = os.getenv("8814863559:AAF1QilzkwOoUzWCF7DR4sxZoqRBioqANog", "8814863559:AAF1QilzkwOoUzWCF7DR4sxZoqRBioqANog")

# Your Telegram user ID — platform owner
PLATFORM_OWNER_IDS: list[int] = [
    int(x.strip()) for x in os.getenv("1899208318", "1899208318").split(",")
    if x.strip().isdigit()
]

# Platform fee percentage (7%)
PLATFORM_FEE_PERCENT = 7
