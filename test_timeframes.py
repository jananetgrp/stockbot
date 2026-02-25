#!/usr/bin/env python3
"""
Test fetching day, week, month, and year comparison data
for BTC, Gold, USD-INR, and DXY from Yahoo Finance.
"""

import requests

HEADERS = {"User-Agent": "Mozilla/5.0"}

SYMBOLS = {
    "BTC":    "BTC-USD",
    "GOLD":   "GC%3DF",
    "USDINR": "INR%3DX",
    "DXY":    "DX-Y.NYB",
}

# ranges: 5d (week), 1mo (month), 1y (year)
# 1d is already handled via regularMarketPrice / previousClose
RANGES = {
    "5d":  {"interval": "1d", "label": "Week"},
    "1mo": {"interval": "1d", "label": "Month"},
    "1y":  {"interval": "1wk", "label": "Year"},
}


def fetch_range(symbol_encoded, range_str, interval):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol_encoded}"
           f"?interval={interval}&range={range_str}")
    r = requests.get(url, headers=HEADERS, timeout=10)
    r.raise_for_status()
    data = r.json()
    result = data["chart"]["result"][0]
    meta = result["meta"]
    price = meta.get("regularMarketPrice")
    closes = result["indicators"]["quote"][0]["close"]
    # First close in the range = the comparison point
    first_close = None
    for c in closes:
        if c is not None:
            first_close = c
            break
    return price, first_close


def main():
    print("Timeframe Comparison Feasibility Test")
    print("=" * 60)

    for name, symbol in SYMBOLS.items():
        print(f"\n{'─'*60}")
        print(f"  {name} ({symbol})")
        print(f"{'─'*60}")

        # Get current price from 1d
        url_1d = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
                  f"?interval=1m&range=1d")
        r = requests.get(url_1d, headers=HEADERS, timeout=10)
        r.raise_for_status()
        meta = r.json()["chart"]["result"][0]["meta"]
        current = meta.get("regularMarketPrice")
        prev_close = meta.get("previousClose")

        if current and prev_close:
            day_chg = ((current - prev_close) / prev_close) * 100
            icon = "▲" if day_chg >= 0 else "▼"
            print(f"  Current:  {current:,.4f}")
            print(f"  Day:      {prev_close:,.4f} → {current:,.4f}  {icon} {day_chg:+.2f}%")
        else:
            print(f"  Current: {current}  (prev_close unavailable)")

        for range_str, cfg in RANGES.items():
            try:
                price, first_close = fetch_range(symbol, range_str, cfg["interval"])
                if first_close and price:
                    chg_pct = ((price - first_close) / first_close) * 100
                    icon = "▲" if chg_pct >= 0 else "▼"
                    print(f"  {cfg['label']:8s}: {first_close:,.4f} → {price:,.4f}  {icon} {chg_pct:+.2f}%")
                else:
                    print(f"  {cfg['label']:8s}: No data")
            except Exception as e:
                print(f"  {cfg['label']:8s}: FAILED — {e}")

    print(f"\n{'='*60}")
    print("Test complete.")


if __name__ == "__main__":
    main()
