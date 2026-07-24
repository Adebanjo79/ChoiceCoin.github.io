# Telegram bot — Robinhood Chain mint address copier

A small Telegram bot that shows your token's **mint / contract address** for Robinhood Chain and lets users copy it in one tap.

## What it does

- `/start` — welcome + current mint address
- `/mint`, `/address`, or `/ca` — show the address with a **Copy mint address** button
- Explorer deep-link so users can verify the contract
- Admin-only `/setaddress`, `/setname`, `/setsymbol`, `/status`

Users paste the copied address into Robinhood Wallet (Swap → paste contract) or any Robinhood Chain trading flow that accepts a contract address.

## Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Get your Telegram user ID from [@userinfobot](https://t.me/userinfobot).
3. Install and configure:

```bash
cd telegram-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

4. Edit `.env`:

```env
BOT_TOKEN=your_bot_token_from_botfather
MINT_ADDRESS=0xYourDeployedContractAddress
TOKEN_NAME=Choice Coin
TOKEN_SYMBOL=CHOICE
ADMIN_IDS=your_telegram_user_id
EXPLORER_URL=https://robinhoodchain.blockscout.com
```

5. Run:

```bash
python bot.py
```

Open Telegram, message your bot, and send `/mint`.

## Admin updates

While the bot is running:

```text
/setaddress 0xNewContractAddress
/setname Choice Coin
/setsymbol CHOICE
/status
```

Address/name/symbol changes are saved to `data/config.json` and survive restarts. `ADMIN_IDS` always comes from `.env`.

## Tests

```bash
cd telegram-bot
source .venv/bin/activate
pytest -q
```

## Notes

- Robinhood Chain is EVM-compatible; addresses must look like `0x` + 40 hex characters.
- This bot only shares and copies an address. It does not mint tokens, trade, or custody funds.
- Always verify the contract on the explorer before swapping.
