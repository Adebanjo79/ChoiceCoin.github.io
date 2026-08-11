# Beginner setup — Football Prediction Bot

## 1. Install Python 3.10+

- Windows: install from python.org (tick “Add to PATH”)
- Linux/macOS: `python3 --version`

## 2. Open the project

```bash
cd football-prediction-bot
```

## 3. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
```

Or on Linux: `bash scripts/setup_linux.sh`

## 4. Run demo tips (no API key)

```bash
python main.py --demo --once
```

You should see a “FOOTBALL DAILY TIPS” report with picks near **3.0 odds** and **≥70% confidence**.

## 5. (Optional) Live fixtures

1. Register at https://www.football-data.org/client/register
2. Paste the token into `.env` as `FOOTBALL_DATA_API_TOKEN=...`
3. Set `DEMO_MODE=false`
4. Run `python main.py --once`

## 6. (Optional) Telegram alerts

1. Message `@BotFather` → create a bot → copy token
2. Message your bot, then get chat id via `@userinfobot` or the getUpdates API
3. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`
4. Test: `python main.py --test-telegram`

## 7. Daily schedule (VPS / always-on with PuTTY)

Full guide: **[VPS_PUTTY_SETUP.md](VPS_PUTTY_SETUP.md)**

Short version:

```bash
python main.py --daemon
```

Runs once immediately, then every day at `RUN_HOUR_UTC` (default 08:00 UTC). Keep it alive with `tmux` so it survives closing PuTTY.
