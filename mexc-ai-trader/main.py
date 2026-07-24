#!/usr/bin/env python3
"""Entry point: 24/7 MEXC Spot AI trading assistant."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings
from src.analysis.engine import format_report
from src.mexc_client import normalize_spot_symbol
from src.scanner import MarketScanner


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(ROOT / "trader.log", encoding="utf-8"),
        ],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="MEXC Spot AI Trading Assistant")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single scan cycle then exit (good for testing in PowerShell)",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="",
        help="Analyze one spot pair only, e.g. BTCUSDT or BTC_USDT",
    )
    parser.add_argument(
        "--print-all",
        action="store_true",
        help="Print every report including NO TRADE (verbose)",
    )
    parser.add_argument(
        "--test-telegram",
        action="store_true",
        help="Send a test message to Telegram and exit",
    )
    args = parser.parse_args()
    setup_logging(settings.log_level)

    scanner = MarketScanner(settings)

    if args.test_telegram:
        from pathlib import Path as _P

        import requests

        env_path = ROOT / ".env"
        token = settings.telegram_bot_token
        chat = settings.telegram_chat_id
        print(f".env path: {env_path}")
        print(f".env exists: {env_path.exists()}")
        print(f"Token length: {len(token)} | has colon (:): {':' in token}")
        if token:
            print(f"Token preview: {token[:6]}...{token[-4:]}")
        else:
            print("Token preview: (empty)")
        print(f"Chat ID: {chat!r}")

        # Validate token with Telegram getMe (does not send a message yet)
        if not token:
            print("FAIL: TELEGRAM_BOT_TOKEN is empty in .env")
            return 1
        if ":" not in token or len(token) < 30:
            print("FAIL: token format looks wrong. Expected like 123456:AAHxxxx...")
            print("Open .env in VS Code/Notepad and paste a fresh token from @BotFather")
            return 1

        try:
            me = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=20)
            print(f"Telegram getMe HTTP: {me.status_code}")
            print(f"Telegram getMe body: {me.text[:300]}")
            if me.status_code == 401 or not me.json().get("ok"):
                print("")
                print("401 = BAD BOT TOKEN.")
                print("Fix:")
                print("1) Telegram -> @BotFather -> /mybots -> your bot -> API Token")
                print("2) Copy FULL token")
                print("3) Edit .env in Notepad (do NOT paste into PowerShell)")
                print("4) Save, then run this test again")
                print("")
                print("PowerShell open .env command:")
                print("  notepad .env")
                return 1
        except Exception as exc:  # noqa: BLE001
            print(f"Could not reach Telegram getMe: {exc}")
            return 1

        ok = scanner.telegram.send(
            "✅ MEXC Spot AI Trader test message.\n"
            "If you see this, Telegram is working.\n"
            f"Account sizing: {settings.account_balance_usdt:.0f} USDT | "
            f"TP3 aim ≈{settings.target_upside_pct:.0f}%\n\n"
            "Next: run  python main.py\n"
            "Then in Telegram type: status\n"
            "(manual live check while the bot is running)"
        )
        print("Telegram OK" if ok else "Telegram FAILED — token OK but send failed (check chat id + press Start on bot)")
        print(f"Token set: {bool(token)} | Chat ID set: {bool(chat)}")
        return 0 if ok else 1

    if args.symbol:
        symbol = normalize_spot_symbol(args.symbol)
        report = scanner.analyze_one(symbol)
        if report is None:
            print("Failed to analyze symbol")
            return 1
        print(format_report(report))
        if report.is_actionable():
            scanner.telegram.send(format_report(report))
        return 0

    if args.once:
        results = scanner.run_scan()
        actionable = [r for r in results if r.is_actionable()]
        print(f"Scanned {len(results)} spot pairs | actionable={len(actionable)}")
        if args.print_all:
            for r in results:
                print("-" * 40)
                print(format_report(r))
        else:
            for r in actionable:
                print("-" * 40)
                print(format_report(r))
        return 0

    scanner.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
