# PuTTY only (no WinSCP) — start from zero

You only need **PuTTY** on Windows.  
The bot is downloaded **directly on the VPS** with git (no ZIP upload).

---

## What you need

| Item | Where from |
|------|------------|
| PuTTY | https://www.putty.org |
| VPS IP + password | Your hosting panel / email |
| API token | football-data.org |

---

## Step 1 — Install PuTTY (Windows)

1. Go to https://www.putty.org  
2. Download the **64-bit Windows installer**  
3. Install (Next → Next → Install)  
4. Open **PuTTY** from the Start menu

---

## Step 2 — Connect to your VPS

1. In PuTTY:
   - **Host Name**: your VPS IP (example `123.45.67.89`)
   - **Port**: `22`
   - Connection type: **SSH**
2. Click **Open**
3. If a security warning appears → **Accept / Yes**
4. `login as:` type `root` → Enter
5. Password: paste with **right-click** → Enter  
   (nothing appears while typing — normal)

You should see a Linux prompt like `root@...:~#`

---

## Step 3 — Install tools (paste in PuTTY)

Right-click in PuTTY to paste. Press Enter after each block.

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git tmux
python3 --version
```

---

## Step 4 — Download the bot on the VPS

```bash
mkdir -p ~/apps
cd ~/apps
git clone https://github.com/Adebanjo79/ChoiceCoin.github.io.git
cd ChoiceCoin.github.io
git fetch origin cursor/football-prediction-bot-53e9
git checkout cursor/football-prediction-bot-53e9
cd football-prediction-bot
ls
```

You should see `main.py` and `requirements.txt`.

---

## Step 5 — Install Python packages

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Step 6 — Add your API token

```bash
cp .env.example .env
nano .env
```

Change these lines:

```env
FOOTBALL_DATA_API_TOKEN=PASTE_YOUR_TOKEN_HERE
DEMO_MODE=false
DAILY_ONLY=true
TIMEZONE=Africa/Lagos
DAILY_INCLUDE_NEXT_HOURS=24
EMPTY_DAY_FALLBACK_DAYS=21
DAYS_AHEAD=1
MIN_CONFIDENCE=70
TARGET_ODDS=3.0
SPORTYBET_ENABLED=true
SPORTYBET_COUNTRY=ng
```

Tips include **SportyBet.com booking codes** you can paste into the SportyBet betslip (Booking Code → Load).

If today has **0 fixtures** (summer break), the bot loads the **next matches within 21 days**.
- Move with arrow keys
- Paste token with **right-click**
- Save: `Ctrl+O` → Enter
- Exit: `Ctrl+X`

Then lock the file:

```bash
chmod 600 .env
```

---

## Step 7 — Test once

```bash
source .venv/bin/activate
python main.py --once
```

Wait 1–2 minutes. You should see **FOOTBALL DAILY TIPS**  
(or “NO TIPS” if nothing meets filters today — that is OK).

Quick demo test (no API):

```bash
python main.py --demo --once
```

---

## Step 8 — Add Telegram (daily tips + status checks)

Full guide: **[TELEGRAM_SETUP.md](TELEGRAM_SETUP.md)**

1. Telegram → `@BotFather` → `/newbot` → copy token  
2. Start your bot, get chat id from `@userinfobot`  
3. Edit `.env`:

```bash
nano .env
```

```env
TELEGRAM_BOT_TOKEN=paste_bot_token
TELEGRAM_CHAT_ID=paste_chat_id
SAFETY_MIN_CONFIDENCE=75
TARGET_ODDS=3.0
MAX_DAILY_TIPS=3
STATUS_INTERVAL_HOURS=6
```

4. Test:

```bash
source .venv/bin/activate
python main.py --test-telegram
```

On Telegram you can always send:
- `/menu` — full command list
- `/fixtures` — today's matches
- `/tips` — full board (≈3 / ≈5 / ≈50)
- `/3odd` `/5odd` `/50odd` — each odds band
- `/codes` — SportyBet booking codes only
- `/safety` — refresh tips + codes now
- `/status` — bot health
- `/ping` — alive check

Full guide: **[TELEGRAM_SETUP.md](TELEGRAM_SETUP.md)**

## Step 9 — Run 24/7 (survive closing PuTTY)

```bash
# If you see "duplicate session: football", the bot is already running.
# Attach to it instead of creating a new one:
tmux attach -t football

# First time only:
tmux new -s football
cd ~/apps/ChoiceCoin.github.io/football-prediction-bot
source .venv/bin/activate
python main.py --daemon
```

**If session already exists and you need a clean restart:**
```bash
tmux kill-session -t football
tmux new -s football
cd ~/apps/ChoiceCoin.github.io/football-prediction-bot
source .venv/bin/activate
python main.py --daemon
```

**Detach** (keep bot running):
1. Press `Ctrl+B`
2. Then press `D`

Now you can close PuTTY. The bot keeps running on the VPS.

**Come back later:**
```bash
tmux attach -t football
```

**Stop bot:** inside tmux press `Ctrl+C`, then type `exit`

---

## Update bot later (optional)

```bash
cd ~/apps/ChoiceCoin.github.io
git pull origin cursor/football-prediction-bot-53e9
cd football-prediction-bot
source .venv/bin/activate
pip install -r requirements.txt
```

Then restart the daemon inside tmux.

---

## Common problems

| Problem | Fix |
|---------|-----|
| Connection timed out | Wrong IP, or VPS not running |
| Access denied / wrong password | Reset password in hosting panel |
| `git: command not found` | Re-run Step 3 install command |
| `No module named ...` | `source .venv/bin/activate` then reinstall requirements |
| Stuck in nano | `Ctrl+X` to exit; save if asked |

---

No WinSCP. No ZIP extract. PuTTY only.
