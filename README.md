# LEAPS Pullback Scanner

Daily scanner that monitors QQQ/SPY for pullbacks from 52-week highs and alerts you via Telegram when individual stocks hit your entry criteria for LEAPS calls.

## Strategy

Buy LEAPS (1-2 year expiry) on strong individual names during broad market pullbacks in a bull market. The scanner watches for pullbacks and sends tiered alerts:

|Tier   |Pullback|Action                                        |
|-------|--------|----------------------------------------------|
|🟡 WATCH|5-7%    |Market dipping — start paying attention       |
|🟠 READY|7-10%   |Research names, prepare orders                |
|🔴 GO   |10%+    |Best LEAPS entry zone — act on strongest names|

## How It Works

1. Checks QQQ and SPY daily for pullback from 52-week high
1. If an index is pulling back ≥5%, scans your watchlist of individual stocks
1. Filters out stocks below their 200-day MA (possible downtrend, not a dip)
1. Sends a Telegram alert grouped by tier with pullback details
1. Deduplicates alerts so you don’t get spammed with the same signal

## Quick Start

```bash
# 1. Clone to your server
git clone <your-repo> && cd leaps-scanner

# 2. Set up Telegram
cp .env.example .env
# Edit .env with your bot token and chat ID

# 3. Test
docker compose run --rm leaps-scanner python scanner.py --test

# 4. Run a scan
docker compose run --rm leaps-scanner python scanner.py

# 5. Start the cron service (runs Mon-Fri after market close)
docker compose up -d leaps-cron
```

## Configuration

Edit the `CONFIG` dict in `scanner.py` to customize:

- **WATCHLIST**: Tickers to scan (default: mega-cap tech + semis)
- **TIER_WATCH/READY/GO**: Pullback thresholds (default: 5/7/10%)
- **REQUIRE_UPTREND**: Only alert if above 200-day MA (default: True)
- **INDEX_TICKERS**: Broad market indexes to monitor (default: QQQ, SPY)

## Cron Schedule

The `leaps-cron` service runs two scans per trading day (UTC times):

- **21:30 UTC** (5:30 PM ET) — After market close, primary scan
- **14:30 UTC** (10:30 AM ET) — Mid-day check for volatile sessions

Adjust times in `docker-compose.yml`. Note: Grande Prairie is MT (UTC-7/UTC-6).

## Commands

```bash
python scanner.py              # Run scan
python scanner.py --test       # Verify Telegram setup
python scanner.py --backtest   # Historical pullback frequency analysis
```

## Future Enhancements

- [ ] RSI and other technical indicators for better entry timing
- [ ] Sector rotation tracking (tech, oil, etc.)
- [ ] VIX level integration (elevated VIX = cheaper LEAPS via higher IV)
- [ ] Interactive Brokers API for portfolio tracking / order staging
- [ ] Web dashboard (could integrate with existing nginx/Docker setup)
