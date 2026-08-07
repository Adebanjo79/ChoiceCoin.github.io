# Robinhood SeaDrop Mint Copier

Watches **SeaDrop** on Robinhood Chain and mints with your wallets when others mint.

## Why the old “copy calldata” path failed

SeaDrop `mintSigned` embeds an EIP-712 server signature that is **bound to the minter wallet** (and a one-time salt). Replaying someone else’s calldata always fails:

```text
Skipped: SeaDrop mintSigned (signature bound to their wallet — not copyable)
```

That skip was correct for raw calldata copy — but it is **not** a dead end.

## Fix: fresh OpenSea signature per wallet

For signed / allowlist stages this bot:

1. Detects the SeaDrop mint (`mintSigned`, `mintAllowList`, …)
2. Resolves the NFT → OpenSea collection slug  
   `GET /api/v2/chain/robinhood/contract/{nft}`
3. For **each of your wallets**, asks OpenSea for a new mint tx  
   `POST /api/v2/drops/{slug}/mint` with `{ minter, quantity }`
4. Signs & broadcasts that wallet-bound calldata

When a **public** stage is active on-chain, it uses `mintPublic` directly (no OpenSea signature).

> Eligibility still applies. If the stage is “OG Robinhood Users” and your wallet is not eligible, OpenSea will reject the mint request — that is expected, not a copy bug.

## Example: VIBE LINGS (`vibelings`)

Target tx: [0x6a584582…](https://robinhoodchain.blockscout.com/tx/0x6a584582bad838572b2da6482dc19c37a746609fb684573686be7fb3ac834551)

| Field | Value |
|-------|--------|
| SeaDrop | `0x00005EA00Ac477B1030CE78506496e8C2dE24bf5` |
| NFT | `0x84d8FbA1F41156FAE5147f2563D52Ef7b31b899d` |
| Method | `mintSigned` |
| Active stage (at mint) | signed_presale — OG Robinhood Users (free, max 2) |
| Public stage | `mintPublic` @ 0.0005 ETH (later) |

## Setup

```bash
cd robinhood-seadrop-copier
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

- `PRIVATE_KEYS` — comma-separated keys for parallel wallets  
- `OPENSEA_API_KEY` — required for signed stages  
- `DRY_RUN=true` until you are ready to broadcast  
- optional `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`

## Commands

```bash
# Check RPC + balances
python main.py status

# Replay the VIBE LINGS mintSigned (dry-run by default)
python main.py replay 0x6a584582bad838572b2da6482dc19c37a746609fb684573686be7fb3ac834551

# Scan recent blocks once
python main.py watch --once --blocks 20

# Live watcher
python main.py watch
```

Set `DRY_RUN=false` only when wallets are funded and you intend to mint.

## Tests

```bash
pytest -q
```

## Safety notes

- Never commit `.env` / private keys.
- Start with `DRY_RUN=true` (eth_call only).
- Signed stages require **your** wallet to be eligible on OpenSea.
- Public `mintPublic` still needs enough ETH for price + gas.