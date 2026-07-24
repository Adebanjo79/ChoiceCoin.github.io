#!/usr/bin/env python3
"""Entry point: 24/7 MEXC Futures AI trading assistant."""

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
    parser = argparse.ArgumentParser(description="MEXC Futures AI Trading Assistant")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single scan cycle then exit (good for testing in PowerShell)",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="",
        help="Analyze one symbol only, e.g. BTC_USDT",
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
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Check .env, MEXC API, and Telegram in one go",
    )
    args = parser.parse_args()
    setup_logging(settings.log_level)

    scanner = MarketScanner(settings)

    if args.diagnose:
        import requests
        from pathlib import Path as P

        print("=== MEXC FUTURES BOT DIAGNOSE ===")
        env_path = P(".env")
        print(f"1) .env exists: {env_path.exists()}")
        print(f"2) Token set: {bool(settings.telegram_bot_token)} | Chat ID: {settings.telegram_chat_id!r}")
        print(f"3) Min confidence: {settings.min_confidence} | mode: {settings.scan_mode}")

        me = scanner.telegram.get_me()
        if me:
            print(f"4) Telegram bot OK: @{me.get('username')} ({me.get('first_name')})")
        else:
            print("4) Telegram bot FAILED — token wrong or network blocked")
            return 1

        scanner.telegram._delete_webhook()
        sent = scanner.telegram.send(
            f"✅ FUTURES bot diagnose OK\nBot: @{me.get('username')}\n"
            "If you see this, open THIS bot chat and type: status"
        )
        print(f"5) Test message sent: {sent}")

        try:
            tick = scanner.client.get_ticker("BTC_USDT")
            price = tick.get("lastPrice") if isinstance(tick, dict) else None
            print(f"6) MEXC Futures API OK | BTC lastPrice={price}")
        except Exception as exc:  # noqa: BLE001
            print(f"6) MEXC Futures API FAILED: {exc}")
            return 1

        print("=== DONE ===")
        print("Next: python main.py   then type status in THIS bot chat only")
        return 0 if sent else 1

    if args.test_telegram:
        ok = scanner.telegram.send(
            "✅ MEXC AI Trader test message.\nIf you see this, Telegram is working."
        )
        print("Telegram OK" if ok else "Telegram FAILED — check TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, and press Start on your bot")
        print(f"Token set: {bool(settings.telegram_bot_token)} | Chat ID set: {bool(settings.telegram_chat_id)}")
        return 0 if ok else 1

    if args.symbol:
        symbol = args.symbol.upper().replace("-", "_")
        if "_" not in symbol and symbol.endswith("USDT"):
            symbol = symbol[:-4] + "_USDT"
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
        print(f"Scanned {len(results)} symbols | actionable={len(actionable)}")
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
