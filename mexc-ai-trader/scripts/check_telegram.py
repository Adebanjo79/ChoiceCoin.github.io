#!/usr/bin/env python3
"""Check Telegram .env token/chat id without sending a trade alert.

Usage (from mexc-ai-trader folder):
  python scripts/check_telegram.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


def clean(value: str | None) -> str:
    return (value or "").strip().strip('"').strip("'").strip()


def main() -> int:
    print(f"Looking for .env at: {ENV_PATH}")
    print(f".env exists: {ENV_PATH.exists()}")
    if not ENV_PATH.exists():
        print("FAIL: no .env file here. Create one from .env.example")
        return 1

    load_dotenv(ENV_PATH, override=True)
    token = clean(os.getenv("TELEGRAM_BOT_TOKEN"))
    chat = clean(os.getenv("TELEGRAM_CHAT_ID"))

    print(f"Token length: {len(token)}")
    print(f"Token has colon (:): {':' in token}")
    print(f"Token preview: {token[:6]}...{token[-4:]}" if len(token) >= 10 else f"Token preview: {token!r}")
    print(f"Chat ID: {chat!r}")

    if not token:
        print("FAIL: TELEGRAM_BOT_TOKEN is empty")
        return 1
    if ":" not in token or len(token) < 30:
        print("FAIL: token format looks wrong. Expected 123456:AAHxxxx...")
        return 1

    print("Calling Telegram getMe ...")
    try:
        resp = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=20)
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: network error: {exc}")
        return 1

    print(f"HTTP status: {resp.status_code}")
    print(f"Body: {resp.text[:400]}")

    if resp.status_code == 401:
        print("")
        print("401 = BAD BOT TOKEN")
        print("1) @BotFather -> /mybots -> your bot -> API Token -> Revoke")
        print("2) Copy NEW token")
        print("3) notepad .env  (edit file, do not paste into PowerShell)")
        print("4) Save, run this script again")
        return 1

    data = {}
    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        pass

    if not data.get("ok"):
        print("FAIL: Telegram did not accept the token")
        return 1

    bot_username = (data.get("result") or {}).get("username")
    print(f"Token OK. Bot username: @{bot_username}")

    if not chat:
        print("WARN: TELEGRAM_CHAT_ID is empty — set it before sending messages")
        return 1

    print("Sending test message ...")
    send = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat, "text": "✅ Telegram check OK. You can now run: python main.py"},
        timeout=20,
    )
    print(f"sendMessage HTTP: {send.status_code}")
    print(f"sendMessage body: {send.text[:400]}")
    if send.ok and send.json().get("ok"):
        print("SUCCESS: check your Telegram chat")
        return 0

    print("Token is valid, but send failed.")
    print("Usually: wrong chat id, or you never pressed Start on the bot.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
