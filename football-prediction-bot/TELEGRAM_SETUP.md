# Telegram setup — check all tips, fixtures & SportyBet codes from your phone

## 1. Create a bot

1. Open Telegram → search **@BotFather**
2. Send `/newbot`
3. Choose a name and username
4. Copy the **token** (looks like `123456:ABC-DEF...`)

## 2. Get your chat id

1. Open your new bot and press **Start**
2. Search **@userinfobot** → Start — it shows your Id  
   OR message your bot, then open:  
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
SPORTYBET_ENABLED=true
SPORTYBET_COUNTRY=ng
DAILY_ONLY=true
TIMEZONE=Africa/Lagos
DEMO_MODE=false
```

Save: `Ctrl+O` → Enter → `Ctrl+X`

## 4. Test Telegram

```bash
source .venv/bin/activate
pip install -r requirements.txt
python main.py --test-telegram
```

You should get a message in Telegram.

## 5. Run 24/7 (this enables all Telegram commands)

```bash
tmux new -s football
cd ~/apps/ChoiceCoin.github.io/football-prediction-bot
source .venv/bin/activate
python main.py --daemon
```

Detach: `Ctrl+B` then `D`

Reattach later: `tmux attach -t football`

## Telegram commands (check everything from the bot)

| Command | What you get |
|---------|----------------|
| `/menu` or `/help` | Full command list |
| `/fixtures` | Today's matches + dates |
| `/tips` | Full board: fixtures + ≈3 / ≈5 / ≈50 + SportyBet codes |
| `/3odd` | Daily ≈3.0 odds + booking code |
| `/5odd` | Daily ≈5.0 odds + booking code |
| `/50odd` | Daily ≈50 odds + booking code |
| `/codes` or `/sportybet` | **Booking codes only** (easy copy/paste) |
| `/safety` or `/refresh` | Fresh scan now (fixtures + tips + codes) |
| `/status` | Bot health / last scan |
| `/ping` | Alive check |

### Typical flow on your phone

1. Open the bot → `/menu`
2. `/safety` — wait for refresh (≈30–90s)
3. `/tips` — see today's board
4. `/codes` — copy SportyBet booking code
5. Open SportyBet → Betslip → Booking Code → Load

## What is pushed automatically

| When | What |
|------|------|
| Bot starts | Online notice + command hint |
| Every day at `RUN_HOUR_UTC` | Full daily board (with SportyBet codes) |
| Every `STATUS_INTERVAL_HOURS` | Status heartbeat |

Only your `TELEGRAM_CHAT_ID` can use the bot.

## Update after new code

```bash
cd ~/apps/ChoiceCoin.github.io
git pull origin cursor/football-prediction-bot-53e9
cd football-prediction-bot
source .venv/bin/activate
pip install -r requirements.txt
# restart daemon
tmux attach -t football
# Ctrl+C, then:
python main.py --daemon
```
