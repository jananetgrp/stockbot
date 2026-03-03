#!/usr/bin/env python3
"""
Feasibility test: Fetch Bitcoin, Gold, USD-INR, and USD Index (DXY)
from Yahoo Finance to verify symbol availability and data format.
"""

import requests
import json
import sys

HEADERS = {"User-Agent": "Mozilla/5.0"}

# Yahoo Finance symbols to test
TEST_SYMBOLS = {
    "Bitcoin (BTC-USD)":    "BTC-USD",
    "Gold Futures (GC=F)":  "GC%3DF",
    "Crude Oil (CL=F)":    "CL%3DF",
    "Silver Futures (SI=F)": "SI%3DF",
    "USD-INR (INR=X)":     "INR%3DX",
    "USD Index DXY (DX-Y.NYB)": "DX-Y.NYB",
}


def test_symbol(label: str, encoded_symbol: str) -> dict | None:
    """Fetch 1d and 5d data for a symbol and report results."""
    url_1d = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}?interval=1m&range=1d"
    url_5d = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}?interval=1d&range=5d"

    print(f"\n{'='*50}")
    print(f"Testing: {label}  (symbol: {encoded_symbol})")
    print(f"{'='*50}")

    # --- 1-day data ---
    try:
        r = requests.get(url_1d, headers=HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        meta = data["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice")
        prev = meta.get("previousClose")
        currency = meta.get("currency", "N/A")
        exchange = meta.get("exchangeName", "N/A")

        if price and prev:
            change = price - prev
            pct = (change / prev) * 100
        else:
            change = pct = None

        print(f"  [1d] Status: OK")
        print(f"  Price:          {price}")
        print(f"  Previous Close: {prev}")
        print(f"  Change:         {change:+.4f}" if change else "  Change:         N/A")
        print(f"  Change %:       {pct:+.4f}%" if pct else "  Change %:       N/A")
        print(f"  Currency:       {currency}")
        print(f"  Exchange:       {exchange}")
    except Exception as e:
        print(f"  [1d] FAILED: {e}")
        return None

    # --- 5-day data ---
    try:
        r5 = requests.get(url_5d, headers=HEADERS, timeout=10)
        r5.raise_for_status()
        data5 = r5.json()
        closes = data5["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        if closes and closes[0] is not None:
            week_ago = closes[0]
            week_change = price - week_ago
            week_pct = (week_change / week_ago) * 100
            print(f"  [5d] Status: OK")
            print(f"  Week-ago Close: {week_ago}")
            print(f"  Week Change:    {week_change:+.4f}")
            print(f"  Week Change %:  {week_pct:+.4f}%")
        else:
            print(f"  [5d] No close data available")
    except Exception as e:
        print(f"  [5d] FAILED: {e}")

    return {"price": price, "prev": prev, "currency": currency, "exchange": exchange}


def main():
    print("Yahoo Finance Symbol Feasibility Test")
    print("=" * 50)

    results = {}
    for label, symbol in TEST_SYMBOLS.items():
        result = test_symbol(label, symbol)
        results[label] = "PASS" if result else "FAIL"

    print(f"\n\n{'='*50}")
    print("SUMMARY")
    print(f"{'='*50}")
    all_pass = True
    for label, status in results.items():
        icon = "✅" if status == "PASS" else "❌"
        print(f"  {icon} {label}: {status}")
        if status == "FAIL":
            all_pass = False

    if all_pass:
        print("\nAll symbols are available! Safe to add to the monitor.")
    else:
        print("\nSome symbols failed. Check alternatives for failed ones.")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
