#!/usr/bin/env bash
# Start BOTH bots on the VPS (Futures + Spot) in separate tmux sessions.
# Run on VPS:  bash scripts/start_both_bots.sh

set -euo pipefail

# FUTURES bot
FUTURES_DIR="${FUTURES_DIR:-$HOME/ChoiceCoin.github.io/mexc-ai-trader}"

# SPOT bot (separate clone of spot branch)
SPOT_DIR="${SPOT_DIR:-$HOME/mexc-spot-bot/mexc-ai-trader}"

FUTURES_SESSION="mexc"
SPOT_SESSION="mexc-spot"

start_in_tmux() {
  local session="$1"
  local workdir="$2"
  local label="$3"

  if [[ ! -d "$workdir" ]]; then
    echo "ERROR: $label folder not found: $workdir"
    if [[ "$label" == "SPOT" ]]; then
      echo "Install spot bot first:"
      echo "  cd ~"
      echo "  git clone -b cursor/mexc-spot-ai-trading-assistant-840c https://github.com/Adebanjo79/ChoiceCoin.github.io.git mexc-spot-bot"
    fi
    exit 1
  fi
  if [[ ! -f "$workdir/main.py" ]]; then
    echo "ERROR: $label main.py not found in: $workdir"
    ls -la "$workdir" || true
    exit 1
  fi

  tmux has-session -t "$session" 2>/dev/null || tmux new-session -d -s "$session" -c "$workdir"
  tmux send-keys -t "$session" C-c
  sleep 1
  tmux send-keys -t "$session" "cd \"$workdir\" && (test -d .venv || python3 -m venv .venv; source .venv/bin/activate; pip install -q -r requirements.txt; python main.py)" Enter
  echo "Started $label in tmux session: $session"
  echo "  path: $workdir"
}

echo "=== Starting Futures + Spot bots ==="
start_in_tmux "$FUTURES_SESSION" "$FUTURES_DIR" "FUTURES"
start_in_tmux "$SPOT_SESSION" "$SPOT_DIR" "SPOT"

sleep 3
echo
echo "=== tmux sessions ==="
tmux ls || true
echo
echo "=== python processes ==="
ps aux | grep -i "python main.py" | grep -v grep || true
echo
echo "Done. Close PuTTY now."
echo "Futures Telegram -> /status"
echo "Spot Telegram -> its own bot chat"
