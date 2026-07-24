# MEXC AI Spot Trading Assistant

Scans **MEXC Spot USDT** pairs around the clock, runs a multi-factor institutional-style checklist, and sends **Telegram** alerts when confidence is **≥ 70%** *and* quality filters pass (BTC calm + volume + not news). Incomplete setups return:

`NO TRADE – WAIT FOR BETTER CONFIRMATION.`

**This build is for SPOT signals (not futures).**  
Default sizing assumes a **50 USDT** account and aims **Take Profit 3** near **~50% price upside** on qualifying setups (more realistic on liquid alts than on BTC).

> Not financial advice. Crypto is high risk. This bot does **not** place orders — it only analyzes and alerts.

**New to this?** Follow: **[BEGINNER_SETUP.md](BEGINNER_SETUP.md)**  
(VS Code → PowerShell test → Telegram → PuTTY/VPS 24/7)

---

## Which tool should you use? (specific answer)

| Tool | Use it for | Do **not** use it for |
|------|------------|------------------------|
| **VS Code** | Writing/editing code, editing `.env`, debugging, reading logs | Running the bot 24/7 unattended |
| **PowerShell** | Installing Python deps on Windows, testing (`--once`, `--symbol`), short local runs while your PC is on | True offline 24/7 (PC sleep/shutdown kills the bot) |
| **PuTTY** | SSH into a **Linux VPS** so the scanner keeps running when your PC is off | Editing large amounts of code (use VS Code locally, then upload/git pull on the VPS) |

### Recommended workflow

1. **Develop & configure on Windows with VS Code**  
   Open the `mexc-ai-trader` folder → edit `.env` → use the integrated terminal (PowerShell).
2. **Test in PowerShell**  
   `python main.py --symbol BTCUSDT` then `python main.py --once`.
3. **Run 24/7 offline on a cheap Linux VPS**  
   Upload/clone the project → connect with **PuTTY** → start under `tmux`/`screen` or a systemd service.  
   Your PC can be off; the VPS keeps scanning.

**Bottom line:**  
- **VS Code** = build / edit  
- **PowerShell** = Windows test (while PC is awake)  
- **PuTTY + VPS** = always-on 24/7 (required for real offline scanning)

Do **not** rely on laptop PowerShell alone if you need signals overnight.

---

## Spot vs futures (what changed)

| Item | This bot (SPOT) |
|------|-----------------|
| Market | MEXC Spot (`api.mexc.com`) |
| Signal side | **BUY (spot)** / **SELL (spot exit)** — no leveraged shorts |
| Futures data | Funding, OI, liquidation heatmap = **N/A** (replaced by Spot Metrics) |
| Account default | `ACCOUNT_BALANCE_USDT=50` |
| Upside goal | `TARGET_UPSIDE_PCT=50` → TP3 aims near +50% price move |
| Position size | 1% account risk, **capped at balance** (no leverage) |

---

## Analysis checklist (all required for a signal)

| Factor | Weight | Checks |
|--------|--------|--------|
| Trend | 25% | EMA 9/20/50/100/200, price vs 200 EMA, 15m/1H/4H/Daily, HH-HL / LH-LL |
| Momentum | 20% | RSI(14)+divergence, MACD, Stoch RSI, ADX(14) > 25 |
| Volume | 15% | ≥1.5× 20-period avg, volume profile POC/HVN/LVN, OBV, CMF |
| Price action | 15% | S/R break + retest, engulfing/pin/star/inside-bar, chop filter |
| Smart Money | 15% | BOS, CHoCH, order blocks, FVG, liquidity sweeps, premium/discount |
| Spot Metrics | 5% | 24h turnover, spread, book imbalance, CVD from trades |
| Fundamentals | 5% | BTC.D / global mcap (CoinGecko), news keywords, macro soft blackout |

**Trade rules enforced in code**

- Default alert threshold **70%**, but only if **quality filters** pass (anti-spam):
  - BTC volatility &lt; `BTC_MAX_VOLATILITY_PCT` (default **1.20**)
  - Volume &gt; 20-period average
  - Not news / macro time
- Reject HTF conflicts, low-liquidity chop  
- Min R:R **1:2.5** (targets use ~1:3), SL beyond structure, size = **1%** account risk  
- Spot only — no futures leverage; TP3 aim ≈ **50%** (`TARGET_UPSIDE_PCT`)

---

## Quick start

### A) Windows — VS Code + PowerShell (testing)

1. Install [Python 3.11+](https://www.python.org/downloads/) (tick **Add to PATH**).
2. Install [VS Code](https://code.visualstudio.com/).
3. In VS Code: **File → Open Folder** → `mexc-ai-trader`.
4. Open **Terminal → New Terminal** (PowerShell) and run:

```powershell
cd mexc-ai-trader
.\scripts\setup_windows.ps1
notepad .env   # or edit in VS Code
```

5. Create a Telegram bot via [@BotFather](https://t.me/BotFather), get `TELEGRAM_BOT_TOKEN`, and put your chat id in `TELEGRAM_CHAT_ID`.
6. Set spot sizing for your goal:

```env
ACCOUNT_BALANCE_USDT=50
TARGET_UPSIDE_PCT=50
MIN_CONFIDENCE=70
QUALITY_FILTERS=true
BTC_MAX_VOLATILITY_PCT=1.20
REQUIRE_VOLUME_ABOVE_AVG=true
TELEGRAM_STATUS=false
```

7. Test:

```powershell
.\.venv\Scripts\Activate.ps1
python main.py --symbol BTCUSDT
python main.py --once
python main.py
```

Optional whitelist:

```env
SYMBOL_WHITELIST=BTCUSDT,ETHUSDT,SOLUSDT
```

### B) 24/7 offline — PuTTY + Linux VPS

1. Rent any small Ubuntu VPS.
2. Install [PuTTY](https://www.putty.org/), connect with host = VPS IP, port 22.
3. On the VPS:

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git tmux
git clone <your-repo-url>
cd mexc-ai-trader
bash scripts/setup_linux.sh
nano .env   # Telegram + ACCOUNT_BALANCE_USDT=50 + TARGET_UPSIDE_PCT=50
```

4. Keep it running after you close PuTTY:

```bash
tmux new -s mexc-spot
source .venv/bin/activate
python main.py
# Detach: Ctrl+b then d
# Re-attach: tmux attach -t mexc-spot
```

---

## CLI

```bash
python main.py                  # 24/7 loop
python main.py --once           # one full market scan
python main.py --symbol BTCUSDT
python main.py --once --print-all
python main.py --test-telegram
```

---

## Telegram signal format (spot)

- Trade direction (**BUY (spot)** / **SELL (spot exit)**)
- Confidence (%)
- Why the trade is valid
- Higher-timeframe trend
- Entry / Stop Loss / TP1 / TP2 / TP3 (~% upside)
- Risk:Reward
- Position size (1% risk, USDT notional)
- Approx USDT gain if TP3 hits
- Estimated holding time
- Invalidation / major risks
- Final verdict: `STRONG BUY` / `BUY` / `WAIT` / `SELL` / `STRONG SELL` / `NO TRADE`

Non-actionable: `NO TRADE – WAIT FOR BETTER CONFIRMATION.`

---

## Project layout

```
mexc-ai-trader/
  main.py                 # entry
  config.py               # env settings (spot defaults)
  src/
    mexc_client.py        # MEXC Spot REST
    scanner.py            # 24/7 scan orchestration
    telegram_alerter.py
    risk.py               # 50 USDT / ~50% TP3 awareness
    analysis/             # trend, momentum, volume, PA, SMC, spot metrics, fundamentals
  scripts/
  tests/
```

---

## API notes / limitations

- Uses **public** MEXC Spot REST (`api.mexc.com`) — no trading keys required for scans.
- Funding / OI / liquidation heatmaps are futures-only and are **not** used.
- **ETF flows**, **DXY**, and **whale/on-chain** feeds need third-party APIs; fundamentals stubs these and still applies BTC.D + news/macro heuristics.
- Set `NEWSAPI_KEY` for live headlines.
- A **50% move** is uncommon on BTC/ETH short-term; the scanner still sizes for your 50 USDT book and will more often find that stretch target on higher-beta alts.
- Scanning every pair every cycle is heavy — start with `SYMBOL_WHITELIST` or `SCAN_TOP_N`.

---

## Tests

```bash
pip install -r requirements.txt
pytest -q
```

---

## Disclaimer

This software is for education and research. Past patterns do not guarantee future results. You are solely responsible for any trading decisions.
