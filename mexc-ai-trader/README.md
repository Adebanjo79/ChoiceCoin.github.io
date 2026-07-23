# MEXC AI Futures Trading Assistant

Scans **MEXC USDT-M Futures** pairs around the clock, runs a multi-factor institutional-style checklist, and sends **Telegram** alerts only when confidence is **≥ 85%**. Incomplete setups return:

`NO TRADE – WAIT FOR BETTER CONFIRMATION.`

> Not financial advice. Crypto futures are high risk. This bot does **not** place orders — it only analyzes and alerts.

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
   `python main.py --symbol BTC_USDT` then `python main.py --once`.
3. **Run 24/7 offline on a cheap Linux VPS**  
   Upload/clone the project → connect with **PuTTY** → start under `tmux`/`screen` or a systemd service.  
   Your PC can be off; the VPS keeps scanning.

**Bottom line:** VS Code = build, PowerShell = Windows test, PuTTY = always-on VPS. For real 24/7, use PuTTY + VPS — not your laptop PowerShell alone.

---

## Analysis checklist (all required for a signal)

| Factor | Weight | Checks |
|--------|--------|--------|
| Trend | 25% | EMA 9/20/50/100/200, price vs 200 EMA, 15m/1H/4H/Daily, HH-HL / LH-LL |
| Momentum | 20% | RSI(14)+divergence, MACD, Stoch RSI, ADX(14) > 25 |
| Volume | 15% | ≥1.5× 20-period avg, volume profile POC/HVN/LVN, OBV, CMF |
| Price action | 15% | S/R break + retest, engulfing/pin/star/inside-bar, chop filter |
| Smart Money | 15% | BOS, CHoCH, order blocks, FVG, liquidity sweeps, premium/discount |
| Futures | 5% | OI snapshot, funding, liquidity, CVD proxy from deals |
| Fundamentals | 5% | BTC.D / global mcap (CoinGecko), news keywords, macro soft blackout |

**Trade rules enforced in code**

- Emit only if confidence ≥ 85% and key factors align  
- Reject HTF conflicts, low-liquidity chop, news blackout windows  
- Min R:R **1:2.5** (targets use ~1:3), SL beyond structure, size = **1%** account risk  

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

5. Create a Telegram bot via [@BotFather](https://t.me/BotFather), get `TELEGRAM_BOT_TOKEN`, and put your chat id in `TELEGRAM_CHAT_ID` (message [@userinfobot](https://t.me/userinfobot)).
6. Test:

```powershell
.\.venv\Scripts\Activate.ps1
python main.py --symbol BTC_USDT
python main.py --once
python main.py
```

Optional: limit pairs in `.env`:

```env
SYMBOL_WHITELIST=BTC_USDT,ETH_USDT,SOL_USDT
```

### B) 24/7 offline — PuTTY + Linux VPS

1. Rent any small Ubuntu VPS ($5/mo class is enough to start; raise CPU if you scan all pairs aggressively).
2. Install [PuTTY](https://www.putty.org/), connect with host = VPS IP, port 22, login `ubuntu`/`root`.
3. On the VPS:

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git tmux
git clone <your-repo-url>
cd mexc-ai-trader
bash scripts/setup_linux.sh
nano .env   # paste Telegram token + chat id
```

4. Keep it running after you close PuTTY:

```bash
tmux new -s mexc
source .venv/bin/activate
python main.py
# Detach: Ctrl+b then d
# Re-attach later: tmux attach -t mexc
```

---

## CLI

```bash
python main.py                  # 24/7 loop
python main.py --once           # one full market scan
python main.py --symbol BTC_USDT
python main.py --once --print-all
```

---

## Telegram signal format

Actionable alerts include: direction, confidence, why valid, HTF trend, entry, SL, TP1–TP3, R:R, 1% position size, holding time, invalidation, risks, final verdict (`STRONG BUY` / `BUY` / `SELL` / `STRONG SELL`).

Non-actionable: `NO TRADE – WAIT FOR BETTER CONFIRMATION.` plus factor scores.

---

## Project layout

```
mexc-ai-trader/
  main.py                 # entry
  config.py               # env settings
  src/
    mexc_client.py        # MEXC Futures REST
    scanner.py            # 24/7 scan orchestration
    telegram_alerter.py
    risk.py
    indicators/
    analysis/             # trend, momentum, volume, PA, SMC, futures, fundamentals, engine
  scripts/
  tests/
```

---

## API notes / limitations

- Uses **public** MEXC Futures REST (`contract.mexc.com`) — no trading keys required for scans.
- **Liquidation heatmaps**, precise **ETF flows**, **DXY**, and **whale/on-chain** feeds need third-party APIs; the fundamentals module stubs these clearly and still applies BTC.D + news/macro heuristics.
- Set `NEWSAPI_KEY` for live headlines; without it, news scoring is limited.
- Scanning *every* pair every cycle is heavy — start with `SYMBOL_WHITELIST` or raise `SCAN_INTERVAL_SECONDS`.

---

## Tests

```bash
pip install -r requirements.txt
pytest -q
```

---

## Disclaimer

This software is for education and research. Past patterns do not guarantee future results. You are solely responsible for any trading decisions.
