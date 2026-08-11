#!/usr/bin/env bash
# Quick VPS health check for the football prediction bot
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== Football bot health check ==="
echo "Time: $(date -u '+%Y-%m-%d %H:%M UTC')"
echo

if [ -f .env ]; then
  echo "OK  .env present"
else
  echo "FAIL  .env missing — copy .env.example and fill tokens"
  exit 1
fi

# shellcheck disable=SC1091
set -a
# shellcheck disable=SC1091
source .env
set +a

[ -n "${FOOTBALL_DATA_API_TOKEN:-}" ] && echo "OK  FOOTBALL_DATA_API_TOKEN set" || echo "WARN  no FOOTBALL_DATA_API_TOKEN (demo mode)"
[ -n "${TELEGRAM_BOT_TOKEN:-}" ] && echo "OK  TELEGRAM_BOT_TOKEN set" || echo "WARN  no TELEGRAM_BOT_TOKEN"
[ -n "${TELEGRAM_CHAT_ID:-}" ] && echo "OK  TELEGRAM_CHAT_ID set" || echo "WARN  no TELEGRAM_CHAT_ID"
echo "    EMPTY_DAY_FALLBACK_DAYS=${EMPTY_DAY_FALLBACK_DAYS:-21 (default)}"
echo "    SPORTYBET_ENABLED=${SPORTYBET_ENABLED:-true}"
echo

if command -v tmux >/dev/null 2>&1; then
  if tmux has-session -t football 2>/dev/null; then
    echo "OK  tmux session 'football' is running"
    echo "    Attach with: tmux attach -t football"
  else
    echo "FAIL  tmux session 'football' NOT running"
    echo "    Start with:"
    echo "      tmux new -s football"
    echo "      source .venv/bin/activate"
    echo "      python main.py --daemon"
  fi
else
  echo "WARN  tmux not installed"
fi
echo

if [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
  echo "Running one tip scan (may take 1–2 min)…"
  python main.py --once
else
  echo "FAIL  .venv missing — run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi
