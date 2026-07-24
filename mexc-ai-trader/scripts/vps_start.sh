#!/usr/bin/env bash
# Start (or restart) the MEXC Spot bot inside tmux so it survives PuTTY disconnect / laptop off.
# Usage on VPS:
#   cd ~/ChoiceCoin.github.io/mexc-ai-trader
#   bash scripts/vps_start.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SESSION="mexc-spot"

cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "ERROR: .env missing in $ROOT"
  echo "Create it first (Telegram token + chat id)."
  exit 1
fi

if [[ ! -d .venv ]]; then
  echo "Creating venv ..."
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -U pip
  pip install -r requirements.txt
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# Kill any old bot process started outside tmux (common laptop-off failure)
pkill -f "python main.py" 2>/dev/null || true
sleep 1

# Recreate clean tmux session
tmux has-session -t "$SESSION" 2>/dev/null && tmux kill-session -t "$SESSION" || true

tmux new-session -d -s "$SESSION" -c "$ROOT"
tmux send-keys -t "$SESSION" "cd '$ROOT' && source .venv/bin/activate && python main.py" C-m

echo "Started bot in tmux session: $SESSION"
echo "Useful commands:"
echo "  tmux ls"
echo "  tmux attach -t $SESSION"
echo "  # detach later: Ctrl+b then d"
echo "  # Telegram: type status"
sleep 2
tmux ls || true
