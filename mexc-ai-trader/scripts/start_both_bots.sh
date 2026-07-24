#!/usr/bin/env bash
# Start BOTH bots on the VPS (Futures + Spot) in separate tmux sessions.
# Run on VPS:  bash scripts/start_both_bots.sh

set -euo pipefail

# FUTURES bot (this repo)
FUTURES_DIR="${FUTURES_DIR:-$HOME/ChoiceCoin.github.io/mexc-ai-trader}"

# SPOT bot (extracted ZIP folder + inner project folder)
# Override if needed:  SPOT_DIR="/your/path" bash scripts/start_both_bots.sh
SPOT_PARENT="${SPOT_PARENT:-$HOME/ChoiceCoin.github.io-cursor-mexc-spot-ai-trading-assistant-840c}"
if [[ -z "${SPOT_DIR:-}" ]]; then
  if [[ -d "$SPOT_PARENT/rootspot ai" ]]; then
    SPOT_DIR="$SPOT_PARENT/rootspot ai"
  elif [[ -d "$SPOT_PARENT/rootspotai" ]]; then
    SPOT_DIR="$SPOT_PARENT/rootspotai"
  elif [[ -d "$SPOT_PARENT/mexc-ai-trader" ]]; then
    SPOT_DIR="$SPOT_PARENT/mexc-ai-trader"
  else
    SPOT_DIR="$SPOT_PARENT"
  fi
fi

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
    echo "Contents:"
    ls -la "$workdir" || true
    exit 1
  fi

  tmux has-session -t "$session" 2>/dev/null || tmux new-session -d -s "$session" -c "$workdir"
  tmux send-keys -t "$session" C-c
  sleep 1
  tmux send-keys -t "$session" "cd \"$workdir\" && (test -d .venv && source .venv/bin/activate; python main.py)" Enter
  echo "Started $label in tmux session: $session"
  echo "  path: $workdir"
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
echo "Futures Telegram bot -> /status"
echo "Spot Telegram bot -> use its own chat"
