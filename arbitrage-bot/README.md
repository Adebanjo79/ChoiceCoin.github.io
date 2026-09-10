# Binance Multi-Market Arbitrage Bot

Paper-first scanner that streams live Binance top-of-book data across 50+ pairs, detects triangular and synthetic-vs-direct mispricings, and simulates fills when **net** edge after fees clears a threshold.

## Reality check

Viral posts claiming “$68 → $750K in days with Claude Code” are not a trustworthy blueprint. On a single liquid venue like Binance, true risk-free arbitrage after taker fees (~10 bps/leg) is rare and competed away by colocated market makers in milliseconds. This project is a **working research/demo system**, not a money printer.

## What it does

- Syncs live `bookTicker` data from Binance WebSocket (public, no API key)
- Scans 50+ spot markets every ~250ms
- Builds triangular routes (e.g. USDT → ETH → BTC → USDT)
- Flags synthetic BTC-route prices vs direct USDT books
- Paper-trades by default from `$68` starting capital
- Serves an iPad-friendly live monitor at `http://localhost:8765`

## Quick start

```bash
cd arbitrage-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```

Open **http://localhost:8765**

## Config

| Variable | Default | Meaning |
|---|---|---|
| `PAPER_TRADING` | `true` | Simulated fills only |
| `STARTING_CAPITAL_USD` | `68` | Paper starting cash |
| `MIN_EDGE_BPS` | `8` | Minimum **net** edge after fees |
| `MAX_POSITION_USD` | `25` | Cap per paper fill |
| `SCAN_SYMBOLS` | ~50 pairs | Markets to stream |

Live trading (`PAPER_TRADING=false`) raises until you add signed Binance order routing — intentional, so the default path cannot place real orders.

## Tests

```bash
cd arbitrage-bot
pytest -q
```

## Architecture

```
arbitrage-bot/
  main.py                 # entrypoint
  config.py               # settings
  src/binance/            # REST exchangeInfo + WS bookTicker
  src/engine/             # book cache, arb math, paper executor
  src/api/server.py       # FastAPI + /ws stream
  src/dashboard/static/   # live monitor UI
  tests/
```

## Disclaimer

Crypto trading is risky. You can lose money. Past screenshots and social posts are not performance guarantees. Use paper mode until you understand fees, latency, partial fills, and inventory risk.
