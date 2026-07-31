#!/usr/bin/env python3
"""Entry point: safest multi-game accus for ≈3 / ≈5 / ≈50 odds + Telegram."""

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
from src.accumulator import format_accumulator_report, format_band_accus
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
        description="Football Acca Bot — safest 1–3 game ≈3.0, 4+ ≈5.0, 7+ ≈50"
    )
    parser.add_argument("--once", action="store_true", help="Run one tip cycle then exit (default)")
    parser.add_argument("--daemon", action="store_true", help="Daily accus + Telegram commands")
    parser.add_argument("--json", action="store_true", help="Print accumulators as JSON")
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
            "✅ Football Acca Bot Telegram OK\n"
            "• Safest ≈3.0 — 1 / 2 / 3 games\n"
            "• ≈5.0 — 4+ games\n"
            "• ≈50 — 7+ games\n"
            "Commands: /tips /3odd /5odd /50odd /status /safety"
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

    all_tips, fixture_count = scanner.analyze_all()
    accus = scanner.select_all_accus(all_tips)
    specs = scanner.acca_specs()

    if args.json:
        print(json.dumps(scanner.export_json(), indent=2))
        return 0

    report = format_accumulator_report(accus, specs)
    scanner._cached_accus = accus
    scanner._cached_report = report
    scanner._cached_band_reports = {
        key: format_band_accus(group, specs[key]) for key, group in accus.items()
    }
    scanner._cached_tips = accus["3odd"][0].legs if accus.get("3odd") else []
    total_legs = sum(a.leg_count for group in accus.values() for a in group)
    scanner.status.mark_scan(
        fixtures=fixture_count,
        predictions=len(all_tips),
        tips=total_legs,
        summary=(
            f"accas 3:{len(accus['3odd'])} 5:{len(accus['5odd'])} "
            f"50:{len(accus['50odd'])}"
        ),
        ok=True,
    )
    print(report)
    if scanner.telegram.enabled:
        if scanner.telegram.send(report):
            scanner.status.mark_telegram_push()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
