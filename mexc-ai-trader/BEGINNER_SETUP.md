# Beginner Setup — Step by Step

Follow this **in order**. Do not skip steps.  
You will use three tools for different jobs:

| Tool | When you use it |
|------|-----------------|
| **VS Code** | Open the project and edit settings |
| **PowerShell** | Install and test the bot on your Windows PC |
| **PuTTY** | Later — connect to a VPS so the bot runs 24/7 when your PC is off |

---

# PART 1 — Install the basics (one time)

## Step 1. Install Python

1. Open your browser and go to: https://www.python.org/downloads/
2. Click the big yellow **Download Python** button.
3. Run the installer.
4. **IMPORTANT:** at the first screen, tick the box **“Add python.exe to PATH”**.
5. Click **Install Now**.
6. When it finishes, click **Close**.

### Check it worked

1. Press the **Windows key**, type `PowerShell`, open **Windows PowerShell**.
2. Type this and press Enter:

```powershell
python --version
```

You should see something like `Python 3.12.x` or `Python 3.11.x`.  
If you see an error, restart the PC and try again. If still failing, reinstall Python and make sure **Add to PATH** is ticked.

---

## Step 2. Install VS Code

1. Go to: https://code.visualstudio.com/
2. Download for Windows and install (Next → Next → Finish is fine).
3. Open **VS Code**.

Optional but helpful: in VS Code, click **Extensions** (left sidebar, square icon) and install:
- **Python** (by Microsoft)

---

## Step 3. Get the project folder on your PC

You need the `mexc-ai-trader` folder on your computer.

### Option A — Download ZIP from GitHub (easiest for beginners)

1. Open the project Pull Request or repo on GitHub.
2. Click the green **Code** button → **Download ZIP**.
3. Unzip it somewhere easy, for example:

`C:\Users\YOURNAME\Desktop\mexc-ai-trader`

(If the ZIP extracted a parent folder first, open it until you see the folder that contains `main.py`, `requirements.txt`, and `README.md`.)

### Option B — Git clone (if you already use Git)

```powershell
cd $HOME\Desktop
git clone https://github.com/Adebanjo79/ChoiceCoin.github.io.git
cd ChoiceCoin.github.io\mexc-ai-trader
```

---

## Step 4. Open the project in VS Code

1. Open **VS Code**.
2. Click **File → Open Folder…**
3. Select the `mexc-ai-trader` folder (the one that contains `main.py`).
4. Click **Select Folder**.
5. If VS Code asks “Do you trust the authors…?”, click **Yes, I trust the authors**.

You should see files on the left: `main.py`, `config.py`, `.env.example`, `src`, etc.

---

# PART 2 — Create your Telegram alert bot

The trading assistant sends messages to **your** Telegram.

## Step 5. Create a bot with BotFather

1. On your phone or PC, open Telegram.
2. Search for **`@BotFather`** (official blue check).
3. Tap **Start**.
4. Send this message:

```text
/newbot
```

5. BotFather asks for a **name**. Example:

```text
My MEXC Signal Bot
```

6. Then it asks for a **username**. It must end with `bot`. Example:

```text
my_mexc_signals_bot
```

7. BotFather replies with a long token that looks like:

```text
7234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

8. **Copy that token** and keep it private. Do not share it.

## Step 6. Get your Chat ID

1. In Telegram, search for **`@userinfobot`**.
2. Tap **Start**.
3. It will reply with your **Id** — a number like `123456789`.
4. Copy that number. That is your `TELEGRAM_CHAT_ID`.

## Step 7. Start a chat with your new bot

1. Search Telegram for the bot username you created (example: `@my_mexc_signals_bot`).
2. Open it and tap **Start**.
3. This unlocks the bot so it can message you.

---

# PART 3 — Configure the bot in VS Code

## Step 8. Create your `.env` file

1. In VS Code left file list, find `.env.example`.
2. Right-click it → **Copy**.
3. Right-click empty space in the file list → **Paste**.
4. Rename the copy to exactly:

```text
.env
```

(Starts with a dot. Name must be `.env`, not `.env.txt`.)

If Windows hides rename tips: right-click → **Rename**.

## Step 9. Fill in your secrets

1. Click `.env` to open it in VS Code.
2. Edit these lines (paste your real values, no quotes):

```env
TELEGRAM_BOT_TOKEN=7234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TELEGRAM_CHAT_ID=123456789
ACCOUNT_BALANCE_USDT=1000
MIN_CONFIDENCE=85
SCAN_INTERVAL_SECONDS=300
MAX_WORKERS=8
SYMBOL_WHITELIST=BTC_USDT,ETH_USDT,SOL_USDT
LOG_LEVEL=INFO
```

### What each setting means (beginner version)

| Setting | Meaning |
|---------|---------|
| `TELEGRAM_BOT_TOKEN` | Password for your Telegram bot |
| `TELEGRAM_CHAT_ID` | Where alerts are sent (your account) |
| `ACCOUNT_BALANCE_USDT` | Used only to calculate 1% risk position size |
| `MIN_CONFIDENCE` | Only alert if score ≥ 85 |
| `SCAN_INTERVAL_SECONDS` | Wait time between full scans (300 = 5 minutes) |
| `SYMBOL_WHITELIST` | **Start here.** Only scan these pairs (faster & safer for beginners) |
| Leave whitelist empty later | Scans all MEXC USDT futures (slower, heavier) |

3. Press **Ctrl + S** to save.

---

# PART 4 — Install and test with PowerShell

## Step 10. Open PowerShell inside VS Code

1. In VS Code top menu: **Terminal → New Terminal**.
2. Make sure the terminal says **PowerShell** (bottom-right of the terminal panel).  
   If it says Command Prompt or Bash, click the dropdown and choose PowerShell.
3. Confirm you are inside `mexc-ai-trader`. You should see that folder name in the path.

If not, type:

```powershell
cd C:\Users\YOURNAME\Desktop\mexc-ai-trader
```

(Use your real path.)

## Step 11. Run the Windows setup script

Paste this and press Enter:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup_windows.ps1
```

What this does:
- creates a private Python environment (`.venv`)
- installs required libraries
- creates `.env` if missing

Wait until you see **Setup complete.**

If you get “running scripts is disabled”, the `Set-ExecutionPolicy` line above fixes it for this session only.

## Step 12. Activate the environment (every new terminal)

Every time you open a new terminal, run:

```powershell
.\.venv\Scripts\Activate.ps1
```

Your prompt should start showing `(.venv)`.

## Step 13. First test — one coin only

```powershell
python main.py --symbol BTC_USDT
```

### What success looks like

You will see a text report in the terminal, for example:

- `Verdict: NO TRADE` (very common — the bot is strict), or
- `BUY` / `SELL` with entry, stop loss, take profits

If Telegram is configured, an actionable signal also goes to Telegram.  
`NO TRADE` may only print in the terminal (that is normal).

### Common beginner errors

| Error | Fix |
|-------|-----|
| `python` not found | Reinstall Python with **Add to PATH**, restart PC |
| `No module named ...` | Run `.\.venv\Scripts\Activate.ps1` then `pip install -r requirements.txt` |
| Telegram not sending | Recheck token/chat id, and tap **Start** on your bot |
| Wrong folder | `cd` into the folder that contains `main.py` |

## Step 14. Second test — scan your whitelist once

```powershell
python main.py --once
```

This scans the pairs in `SYMBOL_WHITELIST` one time, then stops.

## Step 15. Run on your PC (only while PC is awake)

```powershell
python main.py
```

This loops forever. Leave the terminal open.  
To stop: press **Ctrl + C**.

**Important:** if your laptop sleeps or shuts down, the bot stops.  
For true 24/7, continue to Part 5.

---

# PART 5 — Run 24/7 offline (PuTTY + VPS)

Use this when you want the bot running even if your PC is off.

## Step 16. Rent a small Linux VPS

1. Create an account at a VPS provider (examples beginners often use: DigitalOcean, Contabo, Vultr, AWS Lightsail).
2. Create an **Ubuntu** server (22.04 or 24.04).
3. Choose the cheapest plan to start.
4. Save these details somewhere safe:
   - **IP address** (example: `123.45.67.89`)
   - **Username** (often `root` or `ubuntu`)
   - **Password** or SSH key

## Step 17. Install PuTTY on Windows

1. Go to: https://www.putty.org/
2. Download and install PuTTY.
3. Open **PuTTY**.

## Step 18. Connect with PuTTY

1. In **Host Name**, paste your VPS IP.
2. Port: `22`
3. Connection type: **SSH**
4. Click **Open**.
5. If it asks about a security alert the first time, click **Accept**.
6. Login:
   - username = your VPS username
   - password = your VPS password (typing is invisible — that is normal)

You should now see a Linux command prompt.

## Step 19. Install tools on the VPS

Copy/paste these commands one block at a time:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git tmux
```

## Step 20. Put the project on the VPS

### Easiest for beginners: clone with git

```bash
cd ~
git clone https://github.com/Adebanjo79/ChoiceCoin.github.io.git
cd ChoiceCoin.github.io/mexc-ai-trader
bash scripts/setup_linux.sh
```

If your code is only on a PR branch:

```bash
cd ~/ChoiceCoin.github.io
git fetch origin
git checkout cursor/mexc-ai-trading-assistant-04b2
cd mexc-ai-trader
bash scripts/setup_linux.sh
```

## Step 21. Create `.env` on the VPS

```bash
nano .env
```

1. Paste the same values you used on Windows (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, whitelist, etc.).
2. Save in nano:
   - press **Ctrl + O**, then **Enter**
   - press **Ctrl + X** to exit

## Step 22. Test on the VPS

```bash
source .venv/bin/activate
python main.py --symbol BTC_USDT
```

If that works, start 24/7 mode with **tmux** (so closing PuTTY does not kill the bot):

```bash
tmux new -s mexc
source .venv/bin/activate
python main.py
```

### Detach (leave it running)

Press:

`Ctrl + b`  
then release both keys  
then press `d`

You can now close PuTTY. The bot keeps running.

### Come back later

1. Open PuTTY again and log in.
2. Run:

```bash
tmux attach -t mexc
```

### Stop the bot

Inside the tmux session:

```text
Ctrl + C
```

Then:

```bash
exit
```

---

# PART 6 — Daily beginner routine

1. Keep `SYMBOL_WHITELIST` small at first (`BTC_USDT,ETH_USDT,SOL_USDT`).
2. Wait for Telegram alerts (only high-confidence setups).
3. Read every alert: Entry, Stop Loss, TP1/TP2/TP3, Risk:Reward, risks.
4. Decide yourself whether to trade on MEXC — the bot does **not** auto-trade.
5. If you see mostly `NO TRADE`, that is expected. The rules are strict on purpose.

---

# Cheat sheet

### On Windows (PowerShell in VS Code)

```powershell
cd path\to\mexc-ai-trader
.\.venv\Scripts\Activate.ps1
python main.py --symbol BTC_USDT
python main.py --once
python main.py
```

### On VPS (after PuTTY login)

```bash
cd ~/ChoiceCoin.github.io/mexc-ai-trader
tmux attach -t mexc
# or start fresh:
tmux new -s mexc
source .venv/bin/activate
python main.py
```

---

# Safety reminders

- Never share your Telegram bot token.
- Start with small whitelist and paper-check signals before risking money.
- This is not financial advice. Futures can liquidate your account quickly.
- The bot only sends alerts; it does not place orders for you.

---

# Stuck? Checklist

- [ ] Python installed with PATH
- [ ] VS Code opened the folder that contains `main.py`
- [ ] `.env` exists (not `.env.example`)
- [ ] Telegram token + chat id filled
- [ ] You pressed **Start** on your Telegram bot
- [ ] `(.venv)` is active in the terminal
- [ ] For 24/7: bot is running inside `tmux` on a VPS, not only on your laptop
