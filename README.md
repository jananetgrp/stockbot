# Stock Market Monitor

A Raspberry Pi stock market monitor that tracks major indices (S&P 500, DOW, NASDAQ), VIX, and sector ETFs. Compares daily and weekly changes and sends updates via Telegram.

## Features

- Tracks S&P 500, DOW Jones, NASDAQ, VIX, and sector ETFs (Financials, Industrials, Health Care, Real Estate, Utilities)
- Daily and weekly change comparisons
- Analyst-style notes (VIX sentiment, significant movers, sector divergence signals)
- Configurable alert thresholds
- Telegram bot notifications
- Designed to run via cron on a Raspberry Pi

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/your-username/stockbot.git
cd stockbot
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure credentials

Copy the example environment file and fill in your values:

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | Yes | Your Telegram chat or group ID |
| `ALPHA_VANTAGE_KEY` | No | Only needed if `USE_YAHOO=false` |
| `USE_YAHOO` | No | `true` (default) uses Yahoo Finance, no API key needed |
| `CHECK_INTERVAL` | No | Minutes between checks, used in alert messages (default: `15`) |
| `ALERT_CHANGE_PCT` | No | Alert threshold percentage (default: `1.0`, set `0` to disable) |

### 4. Run manually

```bash
python stck_monitor.py
```

### 5. Schedule with cron (Raspberry Pi)

Run every 15 minutes during US market hours (9:30 AM - 4:00 PM ET):

```bash
crontab -e
```

Add:

```
*/15 9-16 * * 1-5 cd /path/to/stockbot && /usr/bin/python3 stck_monitor.py
```

## Project Structure

```
stockbot/
├── stck_monitor.py    # Main script
├── .env               # Your credentials (git-ignored)
├── .env.example       # Credential template
├── .gitignore         # Git ignore rules
├── requirements.txt   # Python dependencies
└── README.md          # This file
```

## How to get your Telegram credentials

1. **Bot Token**: Message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`, follow the prompts, and copy the token.
2. **Chat ID**: Message [@userinfobot](https://t.me/userinfobot) on Telegram and it will reply with your chat ID. For group chats, add the bot to the group and use the Telegram Bot API to get the group chat ID.
