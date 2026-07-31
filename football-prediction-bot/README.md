# Football Prediction Bot

Daily multi-league football tips filtered for **≈3.0 odds** and **≥70% model confidence**.

Covers **Premier League, La Liga, Bundesliga, Ligue 1, Serie A, Eredivisie, Primeira Liga, Championship, Champions League**, and more.

**New to this / using a VPS?** Follow in order:
1. **[PUTTY_ONLY_SETUP.md](PUTTY_ONLY_SETUP.md)** — **PuTTY only** (no WinSCP) ← start here
2. **[TELEGRAM_SETUP.md](TELEGRAM_SETUP.md)** — daily safety 3-odd tips + `/status` commands
3. **[START_HERE_PUTTY.md](START_HERE_PUTTY.md)** — Download ZIP + WinSCP upload path
4. **[BEGINNER_SETUP.md](BEGINNER_SETUP.md)** — short local install notes
5. **[VPS_PUTTY_SETUP.md](VPS_PUTTY_SETUP.md)** — compact VPS reference

### Telegram (daemon mode)

```bash
python main.py --daemon
```

- Uses fixtures from the **next 3 days only** (`DAYS_AHEAD=3`)
- Every leg shows full **date + kickoff (UTC)**
- **Safest ≈3.0** accumulators using **1, 2 or 3 games**
- **≈5.0** accumulators using **4+ games**
- **≈50** accumulators using **7+ games**
- Heartbeat `/status` every `STATUS_INTERVAL_HOURS` (default 6h)
- Commands: `/tips` `/3odd` `/5odd` `/50odd` `/safety` `/status` `/ping`

---

## What it does

1. Loads upcoming fixtures (live API or built-in demo slate)
2. Builds team form from recent results
3. Runs a Poisson expected-goals model across markets (1X2, BTTS, Over/Under, double chance)
4. Scores each pick with a **confidence** checklist
5. Keeps only tips with **confidence ≥ 70** and **odds ≈ 3.0** (± tolerance)
6. Prints a daily report (optional Telegram alert)

Default markets aimed at ~3.0 prices: **Draw, Away Win, Over 2.5, BTTS Yes, X2, Over 3.5**.

---

## Quick start (demo — no API key)

```bash
cd football-prediction-bot
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python main.py --demo --once
```

Useful flags:

| Flag | Purpose |
|------|---------|
| `--demo` | Sample fixtures across EPL / La Liga / Bundesliga / Ligue 1 / Serie A / … |
| `--once` | Single run (default behaviour) |
| `--json` | Machine-readable tips |
| `--all-markets` | Show top raw market scores before filtering |
| `--daemon` | Schedule daily runs at `RUN_HOUR_UTC` |
| `--test-telegram` | Verify Telegram credentials |
| `--min-confidence 70` | Override threshold |
| `--target-odds 3.0` | Override odds target |

---

## Live data setup

1. Free token: [football-data.org](https://www.football-data.org/client/register)
2. Optional book odds: [The Odds API](https://the-odds-api.com)
3. Put keys in `.env`:

```env
FOOTBALL_DATA_API_TOKEN=your_token
ODDS_API_KEY=optional
DEMO_MODE=false
MIN_CONFIDENCE=70
TARGET_ODDS=3.0
ODDS_TOLERANCE=0.75
MAX_DAILY_TIPS=5
LEAGUES=PL,PD,BL1,FL1,SA,DED,PPL,ELC,CL
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

Then:

```bash
python main.py --once
```

---

## Confidence checklist

| Factor | Role |
|--------|------|
| Poisson xG (1X2 / totals / BTTS) | Core probability |
| Recent form (home/away splits) | Adjusts & boosts confidence |
| Edge vs book (or vs naive prior) | Value filter |
| Sample size (≥5 matches) | Data-quality gate |
| League diversification | Max tips spread across competitions |

Only picks that clear **MIN_CONFIDENCE** and sit near **TARGET_ODDS** are published.

---

## Project layout

```
football-prediction-bot/
  main.py                 # CLI entry
  config.py               # .env settings
  src/
    analysis/             # Poisson model + confidence engine
    data/                 # football-data.org, Odds API, demo slate
    selector.py           # Daily ≈3.0 / ≥70% filter
    scanner.py            # Orchestrator
    telegram_alerter.py
  tests/
```

---

## Tests

```bash
pip install -r requirements.txt
pytest
```

---

## Disclaimer

This bot **does not place bets**. Football is uncertain; past form does not guarantee future results. Use responsibly.
