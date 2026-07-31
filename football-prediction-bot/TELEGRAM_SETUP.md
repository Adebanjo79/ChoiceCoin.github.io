# Telegram setup for daily safety 3-odd tips + status commands

## 1. Create a bot

1. Open Telegram
2. Search **@BotFather**
3. Send `/newbot`
4. Choose a name and username
5. Copy the **token** (looks like `123456:ABC-DEF...`)

## 2. Get your chat id

1. Open your new bot and press **Start**
2. Search **@userinfobot** and press Start — it shows your Id  
   OR message your bot, then open in browser:  
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`  
   and find `"chat":{"id": ##########`

## 3. Put both in `.env` on the VPS

```bash
cd ~/apps/ChoiceCoin.github.io/football-prediction-bot
nano .env
```

```env
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_CHAT_ID=123456789
SAFETY_MIN_CONFIDENCE=75
TARGET_ODDS=3.0
MAX_DAILY_TIPS=3
STATUS_INTERVAL_HOURS=6
RUN_HOUR_UTC=8
DEMO_MODE=false
```

Save: `Ctrl+O` → Enter → `Ctrl+X`

## 4. Test Telegram

```bash
source .venv/bin/activate
python main.py --test-telegram
```

You should get a message in Telegram.

## 5. Run 24/7 (tips + status + commands)

```bash
tmux new -s football
cd ~/apps/ChoiceCoin.github.io/football-prediction-bot
source .venv/bin/activate
python main.py --daemon
```

Detach: `Ctrl+B` then `D`

## What you get on Telegram

| When | What |
|------|------|
| Bot starts | Online notice |
| Every day at `RUN_HOUR_UTC` | Full board: best ≈3 / ≈5 / ≈50 odds |
| Every `STATUS_INTERVAL_HOURS` | 📡 Status heartbeat |
| `/tips` | Full multi-band board |
| `/3odd` | Best ≈3.0 safety tips |
| `/5odd` | Best ≈5.0 value tips |
| `/50odd` | Best ≈50 longshots (correct scores) |
| `/safety` | Fresh scan of all bands |
| `/status` | Live health / last scan |
| `/ping` | Quick alive check |

## Commands

```
/start
/help
/status
/tips
/3odd
/5odd
/50odd
/safety
/ping
```

Only your `TELEGRAM_CHAT_ID` can use the bot.
