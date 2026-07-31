#!/usr/bin/env python3
"""Entry point: multi-band football tips (≈3 / ≈5 / ≈50 odds) + Telegram."""

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
from src.selector import format_multi_band_report, short_tips_summary


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
        description="Football Prediction Bot — best ≈3 / ≈5 / ≈50 odds tips + Telegram"
    )
    parser.add_argument("--once", action="store_true", help="Run one tip cycle then exit (default)")
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run forever: daily tips + Telegram commands + status heartbeats",
    )
    parser.add_argument("--json", action="store_true", help="Print multi-band tips as JSON")
    parser.add_argument("--demo", action="store_true", help="Force demo fixtures (no API required)")
    parser.add_argument("--test-telegram", action="store_true", help="Send a Telegram test message")
    parser.add_argument("--status", action="store_true", help="Print / push bot status")
    parser.add_argument("--min-confidence", type=float, default=None, help="Override MIN_CONFIDENCE")
    parser.add_argument("--target-odds", type=float, default=None, help="Override TARGET_ODDS (3-band)")
    args = parser.parse_args()
    setup_logging(settings.log_level)
    cfg = build_config(args)
    scanner = PredictionScanner(cfg)
    scanner.status.mode = "once"

    if args.test_telegram:
        ok = scanner.telegram.send(
            "✅ Football Odds Bot Telegram OK\n"
            f"Bands: ≈{cfg.target_odds:.0f} / ≈{cfg.target_odds_5:.0f} / ≈{cfg.target_odds_50:.0f}\n"
            f"3-odd safety conf ≥ {cfg.safety_min_confidence:.0f}%\n"
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
    bands = scanner.select_all_bands(all_tips)
    meta = scanner.band_defs()

    if args.json:
        print(json.dumps(scanner.export_json(), indent=2))
        return 0

    report = format_multi_band_report(bands, meta)
    scanner._cached_bands = bands
    scanner._cached_report = report
    scanner._cached_tips = bands.get("3odd", [])
    scanner._cached_band_reports = {
        k: scanner.cached_band_report(k) for k in bands
    }
    # rebuild proper per-band reports
    from src.selector import format_daily_report

    scanner._cached_band_reports = {
        key: format_daily_report(
            tips,
            min_confidence=meta[key].min_confidence,
            target_odds=meta[key].target_odds,
            title=meta[key].title,
        )
        for key, tips in bands.items()
    }
    total = sum(len(v) for v in bands.values())
    scanner.status.mark_scan(
        fixtures=fixture_count,
        predictions=len(all_tips),
        tips=total,
        summary=short_tips_summary(bands.get("3odd", [])),
        ok=True,
    )
    print(report)
    if scanner.telegram.enabled:
        if scanner.telegram.send(report):
            scanner.status.mark_telegram_push()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
