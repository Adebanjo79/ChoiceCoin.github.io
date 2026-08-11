# VPS + PuTTY setup (start to finish)

This guide gets the football prediction bot running **24/7 on a Linux VPS** using **PuTTY**.

> Your API token stays in `.env` on the VPS only. Never commit `.env` to GitHub.

---

## What you need

| Item | Purpose |
|------|---------|
| **VPS** | Cheap Linux server (Ubuntu 22.04/24.04) that stays online |
| **PuTTY** | Windows SSH app to connect to the VPS |
| **API token** | football-data.org token (already issued to you) |
| **GitHub repo** | To download the bot code |

---

## Step 1 — Connect with PuTTY

1. Open **PuTTY**
2. Host Name: your VPS IP (example `123.45.67.89`)
3. Port: `22`
4. Connection type: **SSH**
5. Click **Open**
6. Login as `root` (or the user your host gave you)
7. Enter the VPS password

You should see a Linux terminal prompt.

---

## Step 2 — Install Python tools

Paste these commands one block at a time:

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git
python3 --version
```

---

## Step 3 — Download the bot

```bash
cd ~
git clone https://github.com/Adebanjo79/ChoiceCoin.github.io.git
cd ChoiceCoin.github.io
git fetch origin cursor/football-prediction-bot-53e9
git checkout cursor/football-prediction-bot-53e9
cd football-prediction-bot
```

If you already cloned earlier:

```bash
cd ~/ChoiceCoin.github.io
git fetch origin
git checkout cursor/football-prediction-bot-53e9
git pull origin cursor/football-prediction-bot-53e9
cd football-prediction-bot
```

---

## Step 4 — Create virtualenv + install packages

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Step 5 — Add your API token

```bash
cp .env.example .env
nano .env
```

Edit these lines (replace with your real token):

```env
FOOTBALL_DATA_API_TOKEN=YOUR_TOKEN_HERE
DEMO_MODE=false
MIN_CONFIDENCE=70
TARGET_ODDS=3.0
```

In `nano`:
- Edit the text
- Save: `Ctrl+O` then Enter
- Exit: `Ctrl+X`

---

## Step 6 — Test once

```bash
source .venv/bin/activate
python main.py --once
```

You should see **FOOTBALL DAILY TIPS** with live upcoming matches (or `NO TIPS` if nothing meets the 70% / ~3.0 filters today).

---

## Step 7 — Run 24/7 with tmux (recommended)

```bash
sudo apt install -y tmux
tmux new -s football
```

Inside tmux:

```bash
cd ~/ChoiceCoin.github.io/football-prediction-bot
source .venv/bin/activate
python main.py --daemon
```

Detach (bot keeps running after you close PuTTY):

- Press `Ctrl+B`, then `D`

Re-attach later:

```bash
tmux attach -t football
```

Stop the bot (inside the tmux session):

- `Ctrl+C`, then `exit`

---

## Optional — Telegram alerts

1. Telegram → `@BotFather` → `/newbot` → copy token
2. Message your bot, get chat id via `@userinfobot`
3. Edit `.env`:

```env
TELEGRAM_BOT_TOKEN=........
TELEGRAM_CHAT_ID=........
```

4. Test:

```bash
source .venv/bin/activate
python main.py --test-telegram
```

---

## Useful commands cheatsheet

```bash
# enter project
cd ~/ChoiceCoin.github.io/football-prediction-bot
source .venv/bin/activate

# one-shot tips
python main.py --once

# JSON output
python main.py --json

# demo (no API)
python main.py --demo --once

# update code later
cd ~/ChoiceCoin.github.io
git pull
cd football-prediction-bot
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Security notes

- Keep `.env` private on the VPS (`chmod 600 .env`)
- If you pasted your token in a public chat, regenerate it at football-data.org and update `.env`
- Do **not** put the token in GitHub commits or screenshots
