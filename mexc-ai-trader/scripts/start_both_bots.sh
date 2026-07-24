#!/usr/bin/env bash
# Start BOTH bots on the VPS (Futures + Spot) in separate tmux sessions.
# Run on VPS:  bash scripts/start_both_bots.sh

set -euo pipefail

FUTURES_DIR="${FUTURES_DIR:-$HOME/ChoiceCoin.github.io/mexc-ai-trader}"
SPOT_DIR="${SPOT_DIR:-/root/rootspotai}"

FUTURES_SESSION="mexc"
SPOT_SESSION="mexc-spot"

start_in_tmux() {
  local session="$1"
  local workdir="$2"
  local label="$3"

  if [[ ! -d "$workdir" ]]; then
    echo "ERROR: $label folder not found: $workdir"
    exit 1
  fi
  if [[ ! -f "$workdir/main.py" ]]; then
    echo "ERROR: $label main.py not found in: $workdir"
    exit 1
  fi

  tmux has-session -t "$session" 2>/dev/null || tmux new-session -d -s "$session" -c "$workdir"
  # Stop previous python in that session, then start fresh
  tmux send-keys -t "$session" C-c
  sleep 1
  tmux send-keys -t "$session" "cd \"$workdir\" && (test -d .venv && source .venv/bin/activate; python main.py)" Enter
  echo "Started $label in tmux session: $session ($workdir)"
}

echo "=== Starting Futures + Spot bots ==="
start_in_tmux "$FUTURES_SESSION" "$FUTURES_DIR" "FUTURES"
start_in_tmux "$SPOT_SESSION" "$SPOT_DIR" "SPOT"

sleep 2
echo
echo "=== tmux sessions ==="
tmux ls || true
echo
echo "=== python processes ==="
ps aux | grep -i "python main.py" | grep -v grep || true
echo
echo "Done. Close PuTTY now. Both should keep running."
echo "Futures Telegram: /status"
echo "Check spot in its own bot chat."
