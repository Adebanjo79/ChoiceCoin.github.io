#!/usr/bin/env python3
"""Discover your Telegram chat id automatically and save it to .env.

Steps:
1. Make sure TELEGRAM_BOT_TOKEN is set in .env
2. Open your bot in Telegram and tap Start, then send: hi
3. Run:  python scripts/find_chat_id.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


def clean(value: str | None) -> str:
    return (value or "").strip().strip('"').strip("'").strip()


def upsert_env(key: str, value: str) -> None:
    lines: list[str] = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    found = False
    for line in lines:
        if line.startswith(f"{key}="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    load_dotenv(ENV_PATH, override=True)
    token = clean(os.getenv("TELEGRAM_BOT_TOKEN"))
    if not token or ":" not in token:
        print("FAIL: set TELEGRAM_BOT_TOKEN in .env first")
        return 1

    me = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=20)
    if me.status_code == 401 or not me.json().get("ok"):
        print("FAIL: bad bot token (401). Fix TELEGRAM_BOT_TOKEN first.")
        print(me.text[:300])
        return 1

    username = (me.json().get("result") or {}).get("username")
    print(f"Bot OK: @{username}")
    print("")
    print("NOW DO THIS ON YOUR PHONE/PC:")
    print(f"1) Open Telegram and search @{username}")
    print("2) Tap Start")
    print("3) Send a message: hi")
    print("")
    print("Waiting 60 seconds for your message ...")

    # Clear old updates first
    boot = requests.get(
        f"https://api.telegram.org/bot{token}/getUpdates",
        params={"timeout": 0},
        timeout=20,
    )
    offset = 0
    if boot.ok:
        for item in boot.json().get("result", []):
            offset = max(offset, int(item.get("update_id", 0)) + 1)

    deadline = time.time() + 60
    while time.time() < deadline:
        resp = requests.get(
            f"https://api.telegram.org/bot{token}/getUpdates",
            params={"timeout": 20, "offset": offset},
            timeout=35,
        )
        if not resp.ok:
            time.sleep(2)
            continue
        for item in resp.json().get("result", []):
            offset = max(offset, int(item.get("update_id", 0)) + 1)
            message = item.get("message") or item.get("edited_message") or {}
            chat = message.get("chat") or {}
            chat_id = chat.get("id")
            if chat_id is None:
                continue
            chat_id_s = str(chat_id)
            name = (chat.get("first_name") or chat.get("title") or "").strip()
            print("")
            print(f"FOUND chat id: {chat_id_s}  ({name})")
            upsert_env("TELEGRAM_CHAT_ID", chat_id_s)
            print("Saved TELEGRAM_CHAT_ID into .env")

            send = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id_s,
                    "text": "✅ Chat linked. Telegram is working.\nNext: python main.py\nThen type: status",
                },
                timeout=20,
            )
            print(f"Test send: HTTP {send.status_code}")
            print(send.text[:250])
            if send.ok and send.json().get("ok"):
                print("SUCCESS — check Telegram")
                return 0
            print("Chat id saved, but send failed. Try: python main.py --test-telegram")
            return 1
        print("... still waiting, send 'hi' to the bot ...")

    print("")
    print("TIMEOUT: no message received from your bot chat.")
    print(f"Open @{username}, tap Start, send hi, then run this script again.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
