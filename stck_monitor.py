#!/usr/bin/env python3
"""
Stock Market Monitor for Raspberry Pi
Tracks major indices (S&P 500, DOW, NASDAQ), VIX, and sector ETFs
Compares daily and weekly changes, sends updates via Telegram bot
"""

import os
from pathlib import Path

# Load .env file if present (before any config reads)
_env_file = Path(__file__).resolve().parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

import requests
import logging
from datetime import datetime
import pytz

# ─────────────────────────────────────────────
#  CONFIGURATION — set via environment variables or .env file
# ─────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]       # from @BotFather
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]         # your chat / group ID
ALPHA_VANTAGE_KEY  = os.environ.get("ALPHA_VANTAGE_KEY", "")  # free at alphavantage.co

USE_YAHOO      = os.environ.get("USE_YAHOO", "true").lower() == "true"
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "15"))  # minutes between checks

# Alert thresholds (set to 0 to disable)
ALERT_CHANGE_PCT = float(os.environ.get("ALERT_CHANGE_PCT", "1.0"))

# ─────────────────────────────────────────────

LOG_DIR = Path(__file__).resolve().parent
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "stock_monitor.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

CATEGORIES = ["Major Indices", "Volatility", "Sector ETFs"]

SYMBOLS = {
    # ── Major Indices ──
    "SP500"  : {"yahoo": "%5EGSPC", "display": "S&P 500",          "category": "Major Indices"},
    "DOW"    : {"yahoo": "%5EDJI",  "display": "DOW Jones",         "category": "Major Indices"},
    "NASDAQ" : {"yahoo": "%5EIXIC", "display": "NASDAQ",            "category": "Major Indices"},
    # ── Volatility ──
    "VIX"    : {"yahoo": "%5EVIX",  "display": "VIX (Fear Index)",  "category": "Volatility"},
    # ── Sector ETFs ──
    "XLF"    : {"yahoo": "XLF",     "display": "Financials",        "category": "Sector ETFs"},
    "XLI"    : {"yahoo": "XLI",     "display": "Industrials",       "category": "Sector ETFs"},
    "XLV"    : {"yahoo": "XLV",     "display": "Health Care",       "category": "Sector ETFs"},
    "XLRE"   : {"yahoo": "XLRE",    "display": "Real Estate",       "category": "Sector ETFs"},
    "XLU"    : {"yahoo": "XLU",     "display": "Utilities",         "category": "Sector ETFs"},
}

previous_prices: dict = {}


# ─── Data fetching ────────────────────────────

def fetch_yahoo(symbol_encoded: str) -> dict | None:
    """Fetch current price, daily change, and weekly change from Yahoo Finance."""
    headers = {"User-Agent": "Mozilla/5.0"}

    # Fetch current price + previous close from 1d range
    url_1d = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol_encoded}?interval=1m&range=1d"
    # Fetch 5-day daily candles for week-ago close
    url_5d = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol_encoded}?interval=1d&range=5d"

    try:
        r = requests.get(url_1d, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        meta = data["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice")
        prev  = meta.get("previousClose")
        change = price - prev if price and prev else None
        pct    = (change / prev * 100) if change is not None else None

        # Weekly comparison
        week_ago_close = None
        week_change = None
        week_change_pct = None
        try:
            r5 = requests.get(url_5d, headers=headers, timeout=10)
            r5.raise_for_status()
            data5 = r5.json()
            closes = data5["chart"]["result"][0]["indicators"]["quote"][0]["close"]
            # First close in the 5-day window is ~1 week ago
            if closes and closes[0] is not None:
                week_ago_close = closes[0]
                week_change = price - week_ago_close
                week_change_pct = (week_change / week_ago_close * 100) if week_ago_close else None
        except Exception as e:
            log.warning(f"Yahoo 5d fetch error ({symbol_encoded}): {e}")

        return {
            "price": price, "prev_close": prev,
            "change": change, "change_pct": pct,
            "week_ago_close": week_ago_close,
            "week_change": week_change, "week_change_pct": week_change_pct,
        }
    except Exception as e:
        log.error(f"Yahoo fetch error ({symbol_encoded}): {e}")
        return None


def fetch_alpha_vantage(symbol: str) -> dict | None:
    url = (f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE"
           f"&symbol={symbol}&apikey={ALPHA_VANTAGE_KEY}")
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        q = r.json().get("Global Quote", {})
        price  = float(q.get("05. price", 0))
        prev   = float(q.get("08. previous close", 0))
        change = float(q.get("09. change", 0))
        pct    = float(q.get("10. change percent", "0%").replace("%", ""))
        return {"price": price, "prev_close": prev, "change": change, "change_pct": pct}
    except Exception as e:
        log.error(f"Alpha Vantage fetch error ({symbol}): {e}")
        return None


def get_quote(name: str) -> dict | None:
    info = SYMBOLS[name]
    if USE_YAHOO:
        return fetch_yahoo(info["yahoo"])
    else:
        return fetch_alpha_vantage(name)


# ─── Telegram ─────────────────────────────────

def send_telegram(message: str) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id"    : TELEGRAM_CHAT_ID,
        "text"       : message,
        "parse_mode" : "HTML"
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        log.info("Telegram message sent.")
        return True
    except Exception as e:
        log.error(f"Telegram send error: {e}")
        return False


# ─── Helpers ──────────────────────────────────

def arrow(pct: float) -> str:
    if pct is None:
        return "→"
    return "🟢▲" if pct >= 0 else "🔴▼"



def format_number(n: float) -> str:
    return f"{n:,.2f}"


# ─── Core logic ───────────────────────────────

def generate_notes(quotes: dict) -> list[str]:
    """Generate analyst-style notes based on market data."""
    notes = []

    # VIX sentiment
    vix = quotes.get("VIX")
    if vix and vix["price"] is not None:
        v = vix["price"]
        if v >= 30:
            notes.append(f"🔴 VIX at {v:.1f} — <b>High volatility / market fear</b>")
        elif v >= 20:
            notes.append(f"🟡 VIX at {v:.1f} — Elevated uncertainty")
        else:
            notes.append(f"🟢 VIX at {v:.1f} — Market sentiment is calm")

    # Significant daily movers
    for name, q in quotes.items():
        if q is None or q["change_pct"] is None:
            continue
        pct = q["change_pct"]
        display = SYMBOLS[name]["display"]
        if abs(pct) >= 2.0:
            direction = "surged" if pct > 0 else "plunged"
            notes.append(f"⚡ {display} {direction} {pct:+.2f}% today")
        elif abs(pct) >= 1.0:
            direction = "up" if pct > 0 else "down"
            notes.append(f"📈 {display} notably {direction} {pct:+.2f}% today")

    # Significant weekly movers
    for name, q in quotes.items():
        if q is None or q.get("week_change_pct") is None:
            continue
        wpct = q["week_change_pct"]
        display = SYMBOLS[name]["display"]
        if abs(wpct) >= 3.0:
            direction = "rallied" if wpct > 0 else "declined"
            notes.append(f"📊 {display} {direction} {wpct:+.2f}% this week")

    # Sector divergence: Utilities up + Financials down = risk-off
    xlu = quotes.get("XLU")
    xlf = quotes.get("XLF")
    if (xlu and xlf and xlu.get("change_pct") is not None
            and xlf.get("change_pct") is not None):
        if xlu["change_pct"] > 0.3 and xlf["change_pct"] < -0.3:
            notes.append("🛡️ Utilities up, Financials down — risk-off signal")
        elif xlf["change_pct"] > 0.3 and xlu["change_pct"] < -0.3:
            notes.append("🚀 Financials up, Utilities down — risk-on signal")

    return notes


def check_and_notify():
    eastern = pytz.timezone("US/Eastern")
    now_str = datetime.now(eastern).strftime("%Y-%m-%d %H:%M:%S ET")
    lines = [f"📊 <b>Market Update</b>  {now_str}\n"]
    alerts = []
    quotes = {}

    # Fetch all quotes
    for name in SYMBOLS:
        quotes[name] = get_quote(name)

    # Display grouped by category
    for cat in CATEGORIES:
        lines.append(f"\n<b>━━ {cat} ━━</b>")
        cat_symbols = [n for n in SYMBOLS if SYMBOLS[n]["category"] == cat]

        for name in cat_symbols:
            q = quotes[name]
            if q is None:
                lines.append(f"  <b>{SYMBOLS[name]['display']}</b>: ⚠️ data unavailable")
                continue

            price = q["price"]
            pct   = q["change_pct"]
            chg   = q["change"]

            sign = "+" if chg and chg >= 0 else ""
            icon = arrow(pct)
            pct_str = f"{sign}{pct:.2f}%" if pct is not None else "N/A"

            # Weekly change string
            wpct = q.get("week_change_pct")
            if wpct is not None:
                wk_sign = "+" if wpct >= 0 else ""
                wk_str = f"  Wk: {wk_sign}{wpct:.2f}%"
            else:
                wk_str = ""

            line = (f"{icon} <b>{SYMBOLS[name]['display']}</b>: "
                    f"{format_number(price)}  "
                    f"({sign}{format_number(chg) if chg else 'N/A'} "
                    f"{pct_str}){wk_str}")
            lines.append(line)

            # threshold alert
            if ALERT_CHANGE_PCT and pct is not None and abs(pct) >= ALERT_CHANGE_PCT:
                alerts.append(f"⚠️ {SYMBOLS[name]['display']} moved {sign}{pct:.2f}% today!")

            # inter-check delta
            if name in previous_prices and previous_prices[name] is not None:
                prev_price = previous_prices[name]
                delta_pct = (price - prev_price) / prev_price * 100 if prev_price else 0
                if abs(delta_pct) >= 0.5:
                    alerts.append(
                        f"📌 {SYMBOLS[name]['display']} moved "
                        f"{'+' if delta_pct > 0 else ''}{delta_pct:.2f}% in last {CHECK_INTERVAL} min"
                    )

            previous_prices[name] = price

    # Smart notes
    notes = generate_notes(quotes)

    message = "\n".join(lines)
    if notes:
        message += "\n\n<b>📝 Notes:</b>\n" + "\n".join(f"• {n}" for n in notes)
    if alerts:
        message += "\n\n<b>🔔 Alerts:</b>\n" + "\n".join(alerts)

    send_telegram(message)


# ─── Entry point (runs once per cron invocation) ─

def main():
    log.info("Stock monitor triggered by cron.")
    try:
        check_and_notify()
    except Exception as e:
        log.error(f"Unexpected error: {e}")
        send_telegram(f"⚠️ Monitor error: {e}")


if __name__ == "__main__":
    main()