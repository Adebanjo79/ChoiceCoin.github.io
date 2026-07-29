# ETF Retirement Telegram Bot

A Telegram bot that helps you design a **simple long-term retirement plan** by investing a fixed amount each month (default **£100**) into low-cost, diversified stock ETFs.

## Important honesty built into the bot

- **No ETF can guarantee 15% annual gains.** Strong decades happen; reliable forever-15% does not.
- **No stock ETF is crash-proof.** Diversified global funds can still fall 30–50%+ in bad markets.
- The bot’s default advice is: buy a **broad global accumulating ETF** (primary pick **VWRP**) monthly inside a UK **Stocks & Shares ISA**, and stay invested for decades.

This is **educational**, not personalised financial advice.

## Commands

| Command | What it does |
| --- | --- |
| `/start` | Welcome + straight-talk summary |
| `/recommend [monthly] [years] [risk]` | Best ETF plan (`balanced` / `growth` / `calm`) |
| `/plan [monthly] [years] [return%]` | Compound growth projection |
| `/etfs` | Curated ETF catalogue |
| `/etf TICKER` | One ETF in detail |
| `/compare VWRP VUAG` | Side-by-side compare |
| `/reality` | Truth about 15% returns and crashes |
| `/isa` | UK ISA notes |
| `/help` | Command list |

### Examples

```text
/recommend 100 30 balanced
/plan 100 30
/plan 100 30 8
/compare VWRP VUAG SWDA
/etf VWRP
/reality
```

## Default recommendation

For most people investing **£100/month** for retirement:

1. Open a **Stocks & Shares ISA**
2. Buy **VWRP** (Vanguard FTSE All-World, accumulating) every month
3. Keep going for 15–40 years; do not panic-sell crashes

Alternatives the bot knows: `SWDA`, `SSAC`, `VUAG`, `VWRL`, `VFEM`, `VAGP`.

## Setup

1. Message [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token.
2. Install:

```bash
cd etf-retirement-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

3. Put your token in `.env`:

```env
BOT_TOKEN=your_token_from_botfather
```

4. Run:

```bash
python bot.py
```

5. Open Telegram, find your bot, send `/recommend`.

## Tests

```bash
cd etf-retirement-bot
source .venv/bin/activate
pytest -q
```

## Notes

- Tickers are **UK / LSE-oriented** examples commonly used by UK DIY investors.
- Always check the latest OCF, share class (Acc vs Dist), and that your broker supports the ticker.
- Fees, taxes, and personal circumstances matter — this bot cannot know yours.
