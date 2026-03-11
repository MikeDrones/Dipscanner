# #!/usr/bin/env python3
“””
LEAPS Pullback Scanner

Monitors QQQ/SPY for pullbacks from 52-week highs and scans a watchlist
of individual names for LEAPS entry opportunities.

Tiered alert system:

- WATCH  (5-7%)  : Market is pulling back, start paying attention
- READY  (7-10%) : Research individual names, prepare orders
- GO     (10%+)  : Best LEAPS entry zone, act on strongest names

Designed to run as a daily cron job on a Docker server.
Sends alerts via Telegram.

Usage:
python scanner.py              # Run scan
python scanner.py –test       # Send test message to verify Telegram
python scanner.py –backtest   # Show historical pullback analysis
“””

import os
import sys
import json
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path

try:
import yfinance as yf
except ImportError:
print(“ERROR: yfinance not installed. Run: pip install yfinance”)
sys.exit(1)

try:
import requests
except ImportError:
print(“ERROR: requests not installed. Run: pip install requests”)
sys.exit(1)

# —————————————————————————

# Configuration — edit these or override via environment variables

# —————————————————————————

CONFIG = {
# Telegram
“TELEGRAM_BOT_TOKEN”: os.environ.get(“TELEGRAM_BOT_TOKEN”, “YOUR_BOT_TOKEN”),
“TELEGRAM_CHAT_ID”: os.environ.get(“TELEGRAM_CHAT_ID”, “YOUR_CHAT_ID”),

```
# Market index tickers to monitor for broad pullback signals
"INDEX_TICKERS": ["QQQ", "SPY"],

# Individual stock watchlist — strongest names you'd buy LEAPS on
"WATCHLIST": [
    # Mega-cap tech
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    # Semiconductors
    "AMD", "AVGO", "ASML",
    # Other strong names
    "NFLX", "CRM", "COST", "LLY",
],

# Pullback thresholds (percentage from 52-week high)
"TIER_WATCH": 5.0,    # Yellow alert — start watching
"TIER_READY": 7.0,    # Orange alert — research & prepare
"TIER_GO": 10.0,      # Red alert — best entry zone

# Trend filter: only alert if price is above 200-day MA
# (confirms we're in a longer-term uptrend, not a bear market)
"REQUIRE_UPTREND": True,

# Minimum average daily volume (filter out illiquid names)
"MIN_AVG_VOLUME": 1_000_000,

# How many days of history to pull for 52-week high calculation
"LOOKBACK_DAYS": 365,

# State file to avoid duplicate alerts
"STATE_FILE": os.environ.get(
    "SCANNER_STATE_FILE",
    str(Path(__file__).parent / "scanner_state.json"),
),

# Only send alerts once per tier per ticker (reset when price recovers)
"DEDUPLICATE_ALERTS": True,
```

}

# —————————————————————————

# Logging

# —————————————————————————

logging.basicConfig(
level=logging.INFO,
format=”%(asctime)s [%(levelname)s] %(message)s”,
datefmt=”%Y-%m-%d %H:%M:%S”,
)
log = logging.getLogger(“leaps-scanner”)

# —————————————————————————

# Telegram

# —————————————————————————

def send_telegram(message: str, parse_mode: str = “HTML”) -> bool:
“”“Send a message via Telegram Bot API.”””
token = CONFIG[“TELEGRAM_BOT_TOKEN”]
chat_id = CONFIG[“TELEGRAM_CHAT_ID”]

```
if "YOUR_" in token or "YOUR_" in chat_id:
    log.warning("Telegram not configured — printing to stdout instead")
    print(message)
    return False

url = f"https://api.telegram.org/bot{token}/sendMessage"
payload = {
    "chat_id": chat_id,
    "text": message,
    "parse_mode": parse_mode,
    "disable_web_page_preview": True,
}

try:
    resp = requests.post(url, json=payload, timeout=10)
    resp.raise_for_status()
    return True
except Exception as e:
    log.error(f"Telegram send failed: {e}")
    return False
```

# —————————————————————————

# State management (prevents duplicate alerts)

# —————————————————————————

def load_state() -> dict:
“”“Load previous alert state from disk.”””
try:
with open(CONFIG[“STATE_FILE”], “r”) as f:
return json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
return {}

def save_state(state: dict):
“”“Persist alert state to disk.”””
with open(CONFIG[“STATE_FILE”], “w”) as f:
json.dump(state, f, indent=2)

def should_alert(ticker: str, tier: str, state: dict) -> bool:
“”“Check if we should send an alert (avoid duplicates).”””
if not CONFIG[“DEDUPLICATE_ALERTS”]:
return True
key = f”{ticker}:{tier}”
return key not in state

def mark_alerted(ticker: str, tier: str, state: dict):
“”“Record that an alert was sent.”””
key = f”{ticker}:{tier}”
state[key] = datetime.now().isoformat()

def clear_ticker_alerts(ticker: str, state: dict):
“”“Clear all alerts for a ticker when it recovers above thresholds.”””
keys_to_remove = [k for k in state if k.startswith(f”{ticker}:”)]
for k in keys_to_remove:
del state[k]

# —————————————————————————

# Market data

# —————————————————————————

def get_ticker_data(ticker: str) -> dict | None:
“””
Fetch key data for a ticker:
- current price
- 52-week high
- pullback percentage from high
- 200-day moving average
- whether price is above 200-day MA (uptrend)
- average volume
“””
try:
tk = yf.Ticker(ticker)
hist = tk.history(period=“1y”)

```
    if hist.empty or len(hist) < 50:
        log.warning(f"Insufficient data for {ticker}")
        return None

    current_price = hist["Close"].iloc[-1]
    high_52w = hist["High"].max()
    pullback_pct = ((high_52w - current_price) / high_52w) * 100

    # 200-day MA (use whatever we have if less than 200 days)
    ma_200 = hist["Close"].rolling(window=min(200, len(hist))).mean().iloc[-1]
    above_200ma = current_price > ma_200

    # 50-day MA for additional context
    ma_50 = hist["Close"].rolling(window=min(50, len(hist))).mean().iloc[-1]

    avg_volume = hist["Volume"].mean()

    # Date when 52-week high was hit
    high_date = hist["High"].idxmax()

    return {
        "ticker": ticker,
        "price": round(current_price, 2),
        "high_52w": round(high_52w, 2),
        "high_date": high_date.strftime("%Y-%m-%d") if hasattr(high_date, 'strftime') else str(high_date),
        "pullback_pct": round(pullback_pct, 2),
        "ma_200": round(ma_200, 2),
        "ma_50": round(ma_50, 2),
        "above_200ma": above_200ma,
        "avg_volume": int(avg_volume),
    }

except Exception as e:
    log.error(f"Error fetching {ticker}: {e}")
    return None
```

# —————————————————————————

# Alert classification

# —————————————————————————

def classify_pullback(pullback_pct: float) -> str | None:
“”“Classify pullback into tier.”””
if pullback_pct >= CONFIG[“TIER_GO”]:
return “GO”
elif pullback_pct >= CONFIG[“TIER_READY”]:
return “READY”
elif pullback_pct >= CONFIG[“TIER_WATCH”]:
return “WATCH”
return None

def tier_emoji(tier: str) -> str:
return {“WATCH”: “🟡”, “READY”: “🟠”, “GO”: “🔴”}.get(tier, “⚪”)

def tier_label(tier: str) -> str:
return {
“WATCH”: “WATCH (5-7%) — Start paying attention”,
“READY”: “READY (7-10%) — Research & prepare”,
“GO”: “GO (10%+) — Best LEAPS entry zone”,
}.get(tier, “UNKNOWN”)

# —————————————————————————

# Main scan

# —————————————————————————

def run_scan():
“”“Run the full scan and send alerts.”””
log.info(“Starting LEAPS pullback scan…”)
state = load_state()

```
# ---- Phase 1: Check broad market indexes ----
index_alerts = []
for ticker in CONFIG["INDEX_TICKERS"]:
    data = get_ticker_data(ticker)
    if data is None:
        continue

    tier = classify_pullback(data["pullback_pct"])
    if tier:
        index_alerts.append((data, tier))
        log.info(
            f"INDEX {tier_emoji(tier)} {ticker}: "
            f"{data['pullback_pct']}% from 52W high "
            f"(${data['price']} vs ${data['high_52w']})"
        )
    else:
        # Price recovered — clear old alerts
        clear_ticker_alerts(ticker, state)
        log.info(f"INDEX ✅ {ticker}: only {data['pullback_pct']}% from high — no alert")

# ---- Phase 2: If any index is in pullback, scan individual names ----
stock_alerts = []
max_index_tier = None

if index_alerts:
    # Determine the most severe index tier
    tier_rank = {"WATCH": 1, "READY": 2, "GO": 3}
    max_index_tier = max(index_alerts, key=lambda x: tier_rank[x[1]])[1]

    log.info(f"Market pullback detected — scanning {len(CONFIG['WATCHLIST'])} watchlist names...")

    for ticker in CONFIG["WATCHLIST"]:
        data = get_ticker_data(ticker)
        if data is None:
            continue

        # Filter: minimum volume
        if data["avg_volume"] < CONFIG["MIN_AVG_VOLUME"]:
            log.info(f"  SKIP {ticker}: volume too low ({data['avg_volume']:,})")
            continue

        tier = classify_pullback(data["pullback_pct"])
        if tier is None:
            clear_ticker_alerts(ticker, state)
            continue

        # Filter: uptrend check (optional)
        if CONFIG["REQUIRE_UPTREND"] and not data["above_200ma"]:
            log.info(
                f"  SKIP {ticker}: below 200-day MA "
                f"(${data['price']} < ${data['ma_200']}) — possible downtrend"
            )
            continue

        stock_alerts.append((data, tier))
        log.info(
            f"  {tier_emoji(tier)} {ticker}: {data['pullback_pct']}% pullback "
            f"(${data['price']} from ${data['high_52w']})"
        )
else:
    log.info("No significant index pullback detected. Skipping watchlist scan.")

# ---- Phase 3: Build and send Telegram message ----
if not index_alerts and not stock_alerts:
    log.info("All clear — no alerts to send.")
    save_state(state)
    return

# Check which alerts are new
new_index = [(d, t) for d, t in index_alerts if should_alert(d["ticker"], t, state)]
new_stocks = [(d, t) for d, t in stock_alerts if should_alert(d["ticker"], t, state)]

if not new_index and not new_stocks:
    log.info("All alerts already sent previously — nothing new.")
    save_state(state)
    return

# Build message
lines = []
lines.append(f"<b>📊 LEAPS Pullback Scanner</b>")
lines.append(f"<i>{datetime.now().strftime('%Y-%m-%d %H:%M')} MT</i>")
lines.append("")

# Index summary
if index_alerts:
    lines.append("<b>🏛 Market Indexes</b>")
    for data, tier in index_alerts:
        new_tag = " 🆕" if (data, tier) in new_index else ""
        lines.append(
            f"  {tier_emoji(tier)} <b>{data['ticker']}</b>: "
            f"{data['pullback_pct']}% from high "
            f"(${data['price']} / ${data['high_52w']})"
            f"{new_tag}"
        )
    lines.append("")

# Stock alerts grouped by tier
if stock_alerts:
    tier_rank = {"GO": 0, "READY": 1, "WATCH": 2}
    stock_alerts.sort(key=lambda x: (tier_rank[x[1]], -x[0]["pullback_pct"]))

    lines.append("<b>📋 Watchlist Opportunities</b>")
    current_tier = None
    for data, tier in stock_alerts:
        if tier != current_tier:
            current_tier = tier
            lines.append(f"\n  <b>{tier_emoji(tier)} {tier_label(tier)}</b>")

        new_tag = " 🆕" if (data, tier) in new_stocks else ""
        trend = "📈" if data["above_200ma"] else "📉"
        lines.append(
            f"    <b>{data['ticker']}</b>: "
            f"-{data['pullback_pct']}% "
            f"(${data['price']} from ${data['high_52w']}) "
            f"{trend}{new_tag}"
        )
    lines.append("")

# Footer
lines.append("—")
lines.append(
    "<i>LEAPS tip: Look for 1-2yr expiry, "
    "slightly ITM or ATM strikes on strongest names.</i>"
)

message = "\n".join(lines)

# Send
sent = send_telegram(message)
if sent:
    log.info("Telegram alert sent successfully.")
else:
    log.info("Alert printed to stdout (Telegram not configured).")

# Mark alerts as sent
for data, tier in new_index:
    mark_alerted(data["ticker"], tier, state)
for data, tier in new_stocks:
    mark_alerted(data["ticker"], tier, state)

save_state(state)
log.info("Scan complete.")
```

# —————————————————————————

# Backtest mode — show historical pullback frequency

# —————————————————————————

def run_backtest():
“”“Analyze historical pullback frequency for QQQ.”””
log.info(“Running historical pullback analysis for QQQ…”)

```
ticker = "QQQ"
hist = yf.Ticker(ticker).history(period="5y")

if hist.empty:
    log.error("Could not fetch historical data.")
    return

print(f"\n{'='*60}")
print(f"QQQ Pullback Analysis — Last 5 Years")
print(f"{'='*60}")

# Calculate rolling 52-week high and pullback at each point
hist["Rolling_High"] = hist["High"].rolling(window=252, min_periods=1).max()
hist["Pullback_Pct"] = ((hist["Rolling_High"] - hist["Close"]) / hist["Rolling_High"]) * 100

# Find pullback events by year
for year in sorted(hist.index.year.unique()):
    year_data = hist[hist.index.year == year]

    pullbacks_5 = (year_data["Pullback_Pct"] >= 5).sum()
    pullbacks_10 = (year_data["Pullback_Pct"] >= 10).sum()
    pullbacks_15 = (year_data["Pullback_Pct"] >= 15).sum()
    max_pullback = year_data["Pullback_Pct"].max()
    max_date = year_data["Pullback_Pct"].idxmax()

    print(f"\n  {year}:")
    print(f"    Days ≥5% from high:  {pullbacks_5:3d} trading days")
    print(f"    Days ≥10% from high: {pullbacks_10:3d} trading days")
    print(f"    Days ≥15% from high: {pullbacks_15:3d} trading days")
    print(f"    Max pullback:        {max_pullback:.1f}% on {max_date.strftime('%Y-%m-%d')}")

print(f"\n{'='*60}")
print("Takeaway: 5%+ pullbacks happen multiple times per year.")
print("10%+ pullbacks typically happen 1-2x per year.")
print("These are your LEAPS entry zones.")
print(f"{'='*60}\n")
```

# —————————————————————————

# Test mode

# —————————————————————————

def run_test():
“”“Send a test message to verify Telegram setup.”””
msg = (
“<b>🧪 LEAPS Scanner — Test Message</b>\n\n”
“If you see this, your Telegram bot is configured correctly.\n\n”
f”Timestamp: {datetime.now().isoformat()}\n”
f”Watchlist: {len(CONFIG[‘WATCHLIST’])} tickers\n”
f”Indexes: {’, ’.join(CONFIG[‘INDEX_TICKERS’])}”
)
sent = send_telegram(msg)
if sent:
print(“✅ Test message sent successfully!”)
else:
print(“⚠️  Message printed to stdout — configure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID”)

# —————————————————————————

# Entry point

# —————————————————————————

if **name** == “**main**”:
parser = argparse.ArgumentParser(description=“LEAPS Pullback Scanner”)
parser.add_argument(”–test”, action=“store_true”, help=“Send test Telegram message”)
parser.add_argument(”–backtest”, action=“store_true”, help=“Show historical pullback analysis”)
args = parser.parse_args()

```
if args.test:
    run_test()
elif args.backtest:
    run_backtest()
else:
    run_scan()
```
