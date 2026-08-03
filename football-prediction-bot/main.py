#!/usr/bin/env python3
"""Entry point: daily fixtures with ≈3 / ≈5 / ≈50 odds + dates + Telegram."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings
from src.scanner import PredictionScanner


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(ROOT / "predictor.log", encoding="utf-8"),
        ],
    )


def build_config(args: argparse.Namespace):
    cfg = settings
    if args.demo:
        cfg = replace(cfg, demo_mode=True)
    if args.min_confidence is not None:
        cfg = replace(cfg, min_confidence=args.min_confidence)
        cfg = replace(cfg, safety_min_confidence=max(args.min_confidence, cfg.safety_min_confidence))
    if args.target_odds is not None:
        cfg = replace(cfg, target_odds=args.target_odds)
    return cfg


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Daily Fixture Odds Bot — today's matches ≈3 / ≈5 / ≈50 with dates"
    )
    parser.add_argument("--once", action="store_true", help="Run one tip cycle then exit (default)")
    parser.add_argument("--daemon", action="store_true", help="Daily tips + Telegram commands")
    parser.add_argument("--json", action="store_true", help="Print daily board as JSON")
    parser.add_argument("--demo", action="store_true", help="Force demo fixtures")
    parser.add_argument("--test-telegram", action="store_true", help="Send Telegram test message")
    parser.add_argument("--status", action="store_true", help="Print / push bot status")
    parser.add_argument("--min-confidence", type=float, default=None)
    parser.add_argument("--target-odds", type=float, default=None)
    args = parser.parse_args()
    setup_logging(settings.log_level)
    cfg = build_config(args)
    scanner = PredictionScanner(cfg)
    scanner.status.mode = "once"

    if args.test_telegram:
        ok = scanner.telegram.send(
            "✅ Daily Fixture Odds Bot Telegram OK\n"
            f"Timezone: {cfg.timezone_name}\n"
            "Today's fixtures → ≈3 / ≈5 / ≈50 odds with dates\n"
            "Commands: /tips /fixtures /3odd /5odd /50odd /status /safety"
        )
        print("Telegram OK" if ok else "Telegram FAILED — set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID")
        return 0 if ok else 1

    if args.status:
        scanner.status.mode = "status"
        scanner.push_status()
        return 0

    if args.daemon:
        scanner.run_forever()
        return 0

    if args.json:
        print(json.dumps(scanner.export_json(), indent=2))
        return 0

    # Default: one daily board run
    scanner.run_daily(push_telegram=bool(scanner.telegram.enabled))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
