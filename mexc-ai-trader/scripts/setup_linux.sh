#!/usr/bin/env bash
# Linux VPS setup (run after PuTTY SSH login)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env — edit with nano .env"
fi

echo "MEXC SPOT setup complete."
echo "Edit .env: ACCOUNT_BALANCE_USDT=50 TARGET_UPSIDE_PCT=50 + Telegram keys"
echo "Test: python main.py --symbol BTCUSDT"
echo "24/7 with tmux: tmux new -s mexc-spot 'cd $ROOT && source .venv/bin/activate && python main.py'"
