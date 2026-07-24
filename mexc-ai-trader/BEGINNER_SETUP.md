# Beginner Setup — MEXC Spot Signals (Step by Step)

Follow this **in order**. Do not skip steps.

You will use three tools for different jobs:

| Tool | When you use it |
|------|-----------------|
| **VS Code** | Open the project and edit settings (`.env`) |
| **PowerShell** | Install and **test** the bot on your Windows PC |
| **PuTTY** | Later — connect to a VPS so the bot runs **24/7** when your PC is off |

### Specific answer (read this)

- Use **VS Code** to edit code and `.env`.
- Use **PowerShell** (inside VS Code Terminal) to install and test.
- Use **PuTTY + a Linux VPS** for true offline 24/7 scanning.
- Do **not** leave PowerShell running on a sleeping laptop and expect overnight alerts.

**This bot sends SPOT signals (BUY / SELL exit), not futures.**  
Defaults: **50 USDT** account sizing and **~50%** TP3 upside aim.

---

# PART 1 — Install the basics (one time)

## Step 1. Install Python

1. Open https://www.python.org/downloads/
2. Download and run the installer.
3. **IMPORTANT:** tick **“Add python.exe to PATH”**.
4. Install → Close.

Check in PowerShell:

```powershell
python --version
```

You want `Python 3.11+`.

---

## Step 2. Install VS Code

1. https://code.visualstudio.com/
2. Install, then open VS Code.
3. Optional: Extensions → install **Python** (Microsoft).

---

## Step 3. Get the `mexc-ai-trader` folder

### Option A — ZIP from GitHub

Download ZIP → unzip → find the folder that contains `main.py`.

Example path:

`C:\Users\YOURNAME\Desktop\mexc-ai-trader`

### Option B — Git

```powershell
cd $HOME\Desktop
git clone https://github.com/Adebanjo79/ChoiceCoin.github.io.git
cd ChoiceCoin.github.io\mexc-ai-trader
```

If using this PR branch:

```powershell
git fetch origin
git checkout cursor/mexc-spot-ai-trading-assistant-840c
cd mexc-ai-trader
```

---

## Step 4. Open in VS Code

**File → Open Folder…** → select `mexc-ai-trader` (the folder with `main.py`).

---

# PART 2 — Telegram alerts

## Step 5. Create bot with @BotFather

1. Telegram → `@BotFather` → `/newbot`
2. Copy the **token**.

## Step 6. Get chat id

1. Telegram → `@userinfobot` → Start
2. Copy your **Id** number.

## Step 7. Open your bot and tap **Start**

---

# PART 3 — Configure in VS Code

## Step 8–9. Create `.env`

1. Copy `.env.example` → rename to `.env`
2. Edit:

```env
TELEGRAM_BOT_TOKEN=paste_token_here
TELEGRAM_CHAT_ID=paste_chat_id_here
ACCOUNT_BALANCE_USDT=50
TARGET_UPSIDE_PCT=50
MIN_CONFIDENCE=70
QUALITY_FILTERS=true
BTC_MAX_VOLATILITY_PCT=1.20
REQUIRE_VOLUME_ABOVE_AVG=true
SCAN_INTERVAL_SECONDS=300
SCAN_MODE=fast
SYMBOL_WHITELIST=
TELEGRAM_STATUS=false
LOG_LEVEL=INFO
```

| Setting | Meaning |
|---------|---------|
| `ACCOUNT_BALANCE_USDT` | Your spot book (default **50**) — used for 1% risk size |
| `TARGET_UPSIDE_PCT` | TP3 aims near this **% price gain** (default **50**) |
| `MIN_CONFIDENCE` | Use **70** with quality filters (anti-spam) |
| `QUALITY_FILTERS` | Must be `true` at 70%: BTC vol &lt; X, volume &gt; 20-avg, not news time |
| `BTC_MAX_VOLATILITY_PCT` | Your **X** (default `1.20`) — reject if BTC ATR% is higher |
| `SYMBOL_WHITELIST` | Empty = scan liquid spot pairs. Or `BTCUSDT,ETHUSDT` for first tests |

---

# YOUR NEXT STEPS (do in order)

1. **VS Code** → open `mexc-ai-trader` → create `.env` from `.env.example` (values above).
2. **PowerShell** (VS Code terminal):

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup_windows.ps1
.\.venv\Scripts\Activate.ps1
python main.py --test-telegram
python main.py --symbol BTCUSDT
python main.py --once
```

3. If Telegram test works and `--once` finishes, run locally:

```powershell
python main.py
```

4. When you want **24/7 offline**: rent a VPS → **PuTTY** → `tmux` → `python main.py` (Part 5 below).

Save with **Ctrl + S**.

---

# PART 4 — Test with PowerShell (VS Code Terminal)

## Step 10. New Terminal → PowerShell

**Terminal → New Terminal** (choose PowerShell).

## Step 11. Setup

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup_windows.ps1
```

## Step 12. Activate every new terminal

```powershell
.\.venv\Scripts\Activate.ps1
```

## Step 13. Test one spot pair

```powershell
python main.py --symbol BTCUSDT
```

Also works: `BTC_USDT` or `btc/usdt` (normalized to spot).

You will often see `NO TRADE` — that is normal (strict filters).

## Step 14. One full scan

```powershell
python main.py --once
```

## Step 15. Local loop (PC must stay awake)

```powershell
python main.py
```

Stop with **Ctrl + C**.

**Laptop sleep = bot stops.** For real 24/7 → Part 5.

## Step 15b. Ask for status on Telegram (manual)

While `python main.py` is running:

1. Open your bot chat in Telegram  
2. Type:

```text
status
```

(or `/status`)

3. Bot replies with live scan info (cycle, pairs checked, last signal, closest setups)

Keep `TELEGRAM_STATUS=false` so it does **not** spam. You ask `status` only when you want an update.  
Also works: `help`

---

# PART 5 — 24/7 offline (PuTTY + VPS)

## Step 16–18. VPS + PuTTY

1. Rent Ubuntu VPS, save IP / user / password.
2. Install PuTTY → Host = VPS IP → Port 22 → Open → login.

## Step 19–21. Install project on VPS

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git tmux
cd ~
git clone https://github.com/Adebanjo79/ChoiceCoin.github.io.git
cd ChoiceCoin.github.io
git fetch origin
git checkout cursor/mexc-spot-ai-trading-assistant-840c
cd mexc-ai-trader
bash scripts/setup_linux.sh
nano .env
```

Put the same Telegram values + `ACCOUNT_BALANCE_USDT=50` + `TARGET_UPSIDE_PCT=50`.

## Step 22. Run under tmux (survives closing PuTTY / laptop off)

Recommended (background start — safest):

```bash
cd ~/ChoiceCoin.github.io/mexc-ai-trader
git pull origin cursor/mexc-spot-ai-trading-assistant-840c
bash scripts/vps_start.sh
tmux ls
```

Then close PuTTY. Laptop can be off.

In Telegram type: `status`

If you attach to watch logs:

```bash
tmux attach -t mexc-spot
```

Detach before closing PuTTY: `Ctrl+b` then `d`  
(Do not press Ctrl+C unless you want to stop the bot.)

If the bot dies after laptop off, reconnect and run `bash scripts/vps_start.sh` again.

Optional auto-start on VPS reboot:

```bash
sudo cp scripts/mexc-spot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mexc-spot
```

---

# PART 6 — How to read a spot alert

Example meaning for a **50 USDT** book:

- **BUY (spot)** = consider buying the coin on MEXC Spot
- **SELL (spot exit)** = consider selling / taking profit on a holding
- **TP3 ~50%** = stretch target toward +50% price move (more common on alts than BTC)
- **Position size** = sized so you risk ~**1% of 50 USDT = 0.50 USDT** if stop hits
- Bot does **not** auto-buy — you place the order yourself

---

# Cheat sheet

### Windows (PowerShell in VS Code)

```powershell
cd path\to\mexc-ai-trader
.\.venv\Scripts\Activate.ps1
python main.py --test-telegram
python main.py --symbol BTCUSDT
python main.py --once
python main.py
```

### VPS (after PuTTY)

```bash
cd ~/ChoiceCoin.github.io/mexc-ai-trader
tmux attach -t mexc-spot
```

---

# Safety

- Never share your Telegram bot token.
- Spot still loses money — start small and paper-check.
- Not financial advice. Bot alerts only; it does not place orders.
