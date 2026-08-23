# Ink NFT Copy-Mint Bot (Telegram)

Telegram bot that watches target wallets on **Ink Chain** (Ethereum L2, chain id **57073**) and copy-mints **only free public SeaDrop `mintPublic`** from your minting wallets.

> Migrated target: **Ink** (not Robinhood / not a generic “nftboteth” mainnet setup).  
> Explorer: https://explorer.inkonchain.com

## What it copies

| Copy | Skip |
|------|------|
| Free SeaDrop `mintPublic` (`0x161ac21f`) while public window is open and `mintPrice = 0` | `mintSigned` (wallet-bound signature) |
| Rewrites calldata so `minterIfNotPayer = 0x0` (payer receives NFT) | Allowlist / Merkle proof |
| Direct free mint/claim **only if** calldata can be uniquely adapted to our wallet | Paid mints when `FREE_MINTS_ONLY=true` |
| | Closed / not-started (`NotActive` / `0x13da22f2`) |
| | Sold out / per-wallet cap |

## Honest limits

- Cannot forge signed / allowlist proofs.
- Short public windows can still close before all wallets land.
- Pending detection is faster but riskier (reverts waste gas).
- A bad primary RPC fails over to backup; the bot cannot “fix” a garbled node.

## Speed behavior

- Starts copying **before** Telegram alerts.
- Skips receipt fetches for known SeaDrop mint selectors.
- Free SeaDrop path: **one** window/price check — no per-wallet `eth_call` on live blast.
- Prefetches balances + pending nonces; signs locally; `sendRawTransaction` in parallel (~15 wallets).
- On nonce-too-low: refresh nonce, re-sign, retry once.
- Watcher never skips blocks; catch-up in chunks.
- Optional pending/mempool via WebSocket (`PENDING_DETECTION=false` by default).

## Setup (VPS + systemd)

```bash
sudo mkdir -p /opt/nft-copy-bot
sudo rsync -a ./ /opt/nft-copy-bot/
cd /opt/nft-copy-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
cp mint_wallets.json.example mint_wallets.json
# edit .env — TELEGRAM_*, TARGET_WALLETS, PRIVATE_KEYS, keep DRY_RUN=true
sudo cp systemd/nft-copy-bot.service /etc/systemd/system/nft-copy-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now nft-copy-bot
sudo journalctl -u nft-copy-bot -f
```

## Config (`.env`)

| Key | Notes |
|-----|--------|
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_OWNER_ID` | Owner-only commands |
| `RPC_URL`, `RPC_URLS` | Primary + backups (Ink gel / qnd or Alchemy / Chainstack) |
| `CHAIN_ID=57073` | Ink mainnet |
| `TARGET_WALLETS` | Comma-separated wallets to copy |
| `PRIVATE_KEY` / `PRIVATE_KEYS` | Minting keys (+ `/addwallet` → `mint_wallets.json`) |
| `FREE_MINTS_ONLY=true` | Skip paid |
| `DRY_RUN=true` | **Start here** — live only after simulation looks correct |
| `PENDING_DETECTION` + `PENDING_WS_URL` | Optional mempool (off by default) |

Accidental `RPC_URL=` pasted into values is stripped. Alerts label providers by host (Alchemy / Chainstack / Ink public), not hardcoded fake names.

## Commands (owner only)

`/status` `/targets` `/wallets` `/addwallet` `/removewallet` `/pause` `/resume` `/balance` `/help`

## Local commands

```bash
python main.py status
python main.py simulate 0xYOUR_TX
python main.py run
pytest -q
```

## SeaDrop on Ink

Canonical SeaDrop: `0x00005EA00Ac477B1030CE78506496e8C2dE24bf5` (deployed on Ink).  
Collection name comes from the NFT `name()` — SeaDrop’s first calldata arg is the **NFT**, not the SeaDrop router.