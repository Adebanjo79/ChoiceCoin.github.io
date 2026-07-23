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

echo "Test: python main.py --symbol BTC_USDT"
echo "24/7 with tmux: tmux new -s mexc 'cd $ROOT && source .venv/bin/activate && python main.py'"
