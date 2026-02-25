#!/usr/bin/env python3
"""
Stock Market Monitor for Raspberry Pi
Tracks major indices, crypto (BTC), commodities (Gold), forex (USD-INR, DXY),
VIX, and sector ETFs. Compares day/week/month/year changes for key assets.
Sends updates via Telegram bot.
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

CATEGORIES = ["Major Indices", "Crypto", "Commodities", "Forex / USD", "Volatility", "Sector ETFs"]

SYMBOLS = {
    # ── Major Indices ──
    "SP500"  : {"yahoo": "%5EGSPC", "display": "S&P 500",          "category": "Major Indices"},
    "DOW"    : {"yahoo": "%5EDJI",  "display": "DOW Jones",         "category": "Major Indices"},
    "NASDAQ" : {"yahoo": "%5EIXIC", "display": "NASDAQ",            "category": "Major Indices"},
    # ── Crypto ──
    "BTC"    : {"yahoo": "BTC-USD",   "display": "Bitcoin (BTC)",   "category": "Crypto"},
    # ── Commodities ──
    "GOLD"   : {"yahoo": "GC%3DF",    "display": "Gold",            "category": "Commodities"},
    # ── Forex / USD ──
    "USDINR" : {"yahoo": "INR%3DX",   "display": "USD/INR",         "category": "Forex / USD"},
    "DXY"    : {"yahoo": "DX-Y.NYB",  "display": "USD Index (DXY)", "category": "Forex / USD"},
    # ── Volatility ──
    "VIX"    : {"yahoo": "%5EVIX",  "display": "VIX (Fear Index)",  "category": "Volatility"},
    # ── Sector ETFs ──
    "XLF"    : {"yahoo": "XLF",     "display": "Financials",        "category": "Sector ETFs"},
    "XLI"    : {"yahoo": "XLI",     "display": "Industrials",       "category": "Sector ETFs"},
    "XLV"    : {"yahoo": "XLV",     "display": "Health Care",       "category": "Sector ETFs"},
    "XLRE"   : {"yahoo": "XLRE",    "display": "Real Estate",       "category": "Sector ETFs"},
    "XLU"    : {"yahoo": "XLU",     "display": "Utilities",         "category": "Sector ETFs"},
}

TRACKED_SYMBOLS = ["BTC", "GOLD", "USDINR", "DXY"]

previous_prices: dict = {}


# ─── Data fetching ────────────────────────────

def _first_close(closes: list) -> float | None:
    """Return the first non-None close from a list of candle closes."""
    for c in closes:
        if c is not None:
            return c
    return None


def fetch_yahoo(symbol_encoded: str, extended: bool = False) -> dict | None:
    """Fetch current price, daily/weekly change from Yahoo Finance.
    If extended=True, also fetch month and year comparison data."""
    headers = {"User-Agent": "Mozilla/5.0"}

    url_1d = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol_encoded}?interval=1m&range=1d"
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
            first = _first_close(closes)
            if first is not None:
                week_ago_close = first
                week_change = price - week_ago_close
                week_change_pct = (week_change / week_ago_close * 100) if week_ago_close else None
        except Exception as e:
            log.warning(f"Yahoo 5d fetch error ({symbol_encoded}): {e}")

        result = {
            "price": price, "prev_close": prev,
            "change": change, "change_pct": pct,
            "week_ago_close": week_ago_close,
            "week_change": week_change, "week_change_pct": week_change_pct,
        }

        # Extended timeframes: month and year
        if extended and price is not None:
            for range_str, interval, key_prefix in [
                ("1mo", "1d", "month"),
                ("1y", "1wk", "year"),
            ]:
                try:
                    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
                           f"{symbol_encoded}?interval={interval}&range={range_str}")
                    rx = requests.get(url, headers=headers, timeout=10)
                    rx.raise_for_status()
                    dx = rx.json()
                    closes = dx["chart"]["result"][0]["indicators"]["quote"][0]["close"]
                    first = _first_close(closes)
                    if first is not None:
                        result[f"{key_prefix}_ago_close"] = first
                        result[f"{key_prefix}_change"] = price - first
                        result[f"{key_prefix}_change_pct"] = (price - first) / first * 100
                    else:
                        result[f"{key_prefix}_ago_close"] = None
                        result[f"{key_prefix}_change"] = None
                        result[f"{key_prefix}_change_pct"] = None
                except Exception as e:
                    log.warning(f"Yahoo {range_str} fetch error ({symbol_encoded}): {e}")
                    result[f"{key_prefix}_ago_close"] = None
                    result[f"{key_prefix}_change"] = None
                    result[f"{key_prefix}_change_pct"] = None

        return result
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
        extended = name in TRACKED_SYMBOLS
        return fetch_yahoo(info["yahoo"], extended=extended)
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

    # Bitcoin sentiment
    btc = quotes.get("BTC")
    if btc and btc["price"] is not None:
        btc_pct = btc.get("change_pct")
        if btc_pct is not None:
            if btc_pct >= 5:
                notes.append(f"🚀 Bitcoin surging {btc_pct:+.2f}% — strong crypto momentum")
            elif btc_pct <= -5:
                notes.append(f"💥 Bitcoin dropping {btc_pct:+.2f}% — crypto sell-off")
        btc_price = btc["price"]
        if btc_price >= 100000:
            notes.append(f"🪙 Bitcoin above $100K at ${btc_price:,.0f}")

    # Gold sentiment
    gold = quotes.get("GOLD")
    if gold and gold.get("change_pct") is not None:
        gold_pct = gold["change_pct"]
        if gold_pct >= 1.5:
            notes.append(f"🥇 Gold rallying {gold_pct:+.2f}% — safe-haven demand")
        elif gold_pct <= -1.5:
            notes.append(f"📉 Gold falling {gold_pct:+.2f}% — risk appetite returning")

    # USD strength via DXY
    dxy = quotes.get("DXY")
    if dxy and dxy.get("change_pct") is not None:
        dxy_pct = dxy["change_pct"]
        if dxy_pct >= 0.5:
            notes.append(f"💵 USD strengthening (DXY {dxy_pct:+.2f}%) — headwind for commodities")
        elif dxy_pct <= -0.5:
            notes.append(f"📉 USD weakening (DXY {dxy_pct:+.2f}%) — tailwind for commodities")

    # USD-INR movement
    usdinr = quotes.get("USDINR")
    if usdinr and usdinr.get("change_pct") is not None:
        inr_pct = usdinr["change_pct"]
        if inr_pct >= 0.3:
            notes.append(f"🇮🇳 Rupee weakening vs USD ({inr_pct:+.2f}%)")
        elif inr_pct <= -0.3:
            notes.append(f"🇮🇳 Rupee strengthening vs USD ({inr_pct:+.2f}%)")

    # Sector divergence: Utilities up + Financials down = risk-off
    xlu = quotes.get("XLU")
    xlf = quotes.get("XLF")
    if (xlu and xlf and xlu.get("change_pct") is not None
            and xlf.get("change_pct") is not None):
        if xlu["change_pct"] > 0.3 and xlf["change_pct"] < -0.3:
            notes.append("🛡️ Utilities up, Financials down — risk-off signal")
        elif xlf["change_pct"] > 0.3 and xlu["change_pct"] < -0.3:
            notes.append("🚀 Financials up, Utilities down — risk-on signal")

    # Cross-asset: Gold up + USD down = inflation hedge signal
    if (gold and dxy and gold.get("change_pct") is not None
            and dxy.get("change_pct") is not None):
        if gold["change_pct"] > 0.5 and dxy["change_pct"] < -0.3:
            notes.append("🛡️ Gold up + USD down — inflation hedge / risk-off positioning")

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

    # ── Timeframe comparison for tracked symbols ──
    lines.append("\n<b>━━ Timeframe Comparison ━━</b>")
    timeframes = [
        ("change_pct",       "Day"),
        ("week_change_pct",  "Wk"),
        ("month_change_pct", "Mo"),
        ("year_change_pct",  "Yr"),
    ]
    for name in TRACKED_SYMBOLS:
        q = quotes.get(name)
        if q is None:
            lines.append(f"  <b>{SYMBOLS[name]['display']}</b>: ⚠️ data unavailable")
            continue
        display = SYMBOLS[name]["display"]
        parts = []
        for key, label in timeframes:
            val = q.get(key)
            if val is not None:
                icon = "🟢" if val >= 0 else "🔴"
                parts.append(f"{label}: {icon}{val:+.2f}%")
            else:
                parts.append(f"{label}: —")
        lines.append(f"  <b>{display}</b>")
        lines.append(f"    {' │ '.join(parts)}")

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