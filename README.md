# ⭐ Stars Payment Platform — Father Bot

A multi-tenant Telegram Stars payment platform. Users connect their bots, create payment links, and the platform automatically charges a 7% fee per transaction.

---

## Architecture

```
Father Bot (you)
├── User A registers @their_bot → child bot starts inside your server
│   ├── /createlink 100 VIP → generates https://t.me/$... link
│   ├── Buyer pays 100 stars
│   ├── Buyer gets custom message
│   ├── User A gets notified (receives 93 stars net)
│   └── Father bot auto-sends 7 star fee invoice to User A ✅
└── User B registers @another_bot → same flow
```

---

## Setup

### 1. Create the father bot
- `/newbot` in @BotFather → get token
- Enable Stars: Payments → Telegram Stars

### 2. Configure
Edit `config.py`:
```python
FATHER_BOT_TOKEN = "your_father_bot_token"
PLATFORM_OWNER_IDS = [your_telegram_id]
```

### 3. Install & run
```bash
pip install -r requirements.txt
python father_bot.py
```

---

## User Flow (sub-admin)

1. User opens your father bot
2. `/addbot` → sends their bot token
3. Father bot validates token, starts the child bot live
4. User goes to their bot and uses:
   - `/createlink 50 VIP Access` → gets a `https://t.me/$...` link
   - `/setmessage <id> Thanks! Here's your link: ...` → custom reply
   - `/links` → see all links
   - `/stats` → earnings
5. They share the link anywhere
6. When someone pays → buyer gets custom message
7. **Father bot automatically sends a Stars fee invoice to the sub-admin**

---

## Fee System

- Fee = 7% of payment amount (minimum 1 star)
- Charged automatically after every payment
- Father bot sends an inline Stars invoice directly to the sub-admin
- Sub-admin pays it instantly inside Telegram

---

## Platform Owner Commands

| Command | Description |
|---|---|
| `/platformstats` | Total bots, payments, stars, fees collected |

---

## Files

| File | Purpose |
|---|---|
| `father_bot.py` | Main platform bot |
| `child_runner.py` | Dynamically spawns/manages child bots |
| `db.py` | SQLite database (bots, links, payments, fees) |
| `config.py` | Token + owner IDs + fee % |
| `platform.db` | Auto-created SQLite database |
