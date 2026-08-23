#!/usr/bin/env bash
# Apply TARGET_WALLETS + PRIVATE_KEYS into the Ink bot .env only.
# Does not touch any Robinhood bot path/service.
set -euo pipefail

INK_DIR="${INK_DIR:-/opt/ink-nft-copy-bot}"
ENV_FILE="${INK_DIR}/.env"
SERVICE="${INK_SERVICE:-ink-nft-copy-bot}"

if [[ ! -f "$ENV_FILE" ]]; then
  # Fallback if you installed into the older path for Ink only
  if [[ -f /opt/nft-copy-bot/.env ]] && grep -q 'CHAIN_ID=57073' /opt/nft-copy-bot/.env 2>/dev/null; then
    INK_DIR=/opt/nft-copy-bot
    ENV_FILE=/opt/nft-copy-bot/.env
    SERVICE=nft-copy-bot
    echo "Using Ink install at $INK_DIR (service=$SERVICE)"
  else
    echo "Missing $ENV_FILE — install the Ink bot first."
    exit 1
  fi
fi

if [[ -z "${TARGET_WALLETS:-}" ]]; then
  echo "Set TARGET_WALLETS first, e.g.:"
  echo "  export TARGET_WALLETS='0xabc...,0xdef...'"
  exit 1
fi

if [[ -z "${PRIVATE_KEYS:-}" ]]; then
  echo "Set PRIVATE_KEYS first, e.g.:"
  echo "  export PRIVATE_KEYS='0xkey1,0xkey2'"
  exit 1
fi

# Refuse to run if this .env looks like Robinhood (chain 4663)
if grep -qE '^CHAIN_ID=4663\b' "$ENV_FILE"; then
  echo "Refusing: $ENV_FILE is Robinhood (CHAIN_ID=4663). Use the Ink bot directory."
  exit 1
fi

python3 - "$ENV_FILE" <<'PY'
import os, sys, re
from pathlib import Path
path = Path(sys.argv[1])
text = path.read_text()
updates = {
    "TARGET_WALLETS": os.environ["TARGET_WALLETS"].strip(),
    "PRIVATE_KEYS": os.environ["PRIVATE_KEYS"].strip(),
    "DRY_RUN": os.environ.get("DRY_RUN", "true").strip() or "true",
}
for key, value in updates.items():
    pat = re.compile(rf"^{re.escape(key)}=.*$", re.M)
    line = f"{key}={value}"
    if pat.search(text):
        text = pat.sub(line, text)
    else:
        text = text.rstrip() + "\n" + line + "\n"
path.write_text(text)
# Print only safe metadata
tw = [x.strip() for x in updates["TARGET_WALLETS"].replace("\n", ",").split(",") if x.strip()]
pk = [x.strip() for x in updates["PRIVATE_KEYS"].replace("\n", ",").split(",") if x.strip()]
print(f"Updated {path}")
print(f"TARGET_WALLETS count={len(tw)}")
for i, a in enumerate(tw):
    print(f"  [{i}] {a[:6]}…{a[-4:]}")
print(f"PRIVATE_KEYS count={len(pk)} (values not printed)")
print(f"DRY_RUN={updates['DRY_RUN']}")
PY

echo
echo "Restarting Ink service only: $SERVICE"
if systemctl list-unit-files | grep -q "^${SERVICE}.service"; then
  sudo systemctl restart "$SERVICE"
  sudo systemctl status "$SERVICE" --no-pager | head -20
else
  echo "systemd unit $SERVICE not found — start manually:"
  echo "  cd $INK_DIR && source .venv/bin/activate && python main.py run"
fi

echo
echo "In Telegram: /status then /targets then /wallets"
echo "Robinhood bot was not restarted."
