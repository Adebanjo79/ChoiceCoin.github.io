#!/usr/bin/env python3
"""Entry point: multi-league football prediction bot (≈3.0 odds, safety tips + Telegram)."""

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
from src.selector import format_daily_report, select_daily_tips


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
        description="Football Prediction Bot — safety ≈3.0 odds tips + Telegram status"
    )
    parser.add_argument("--once", action="store_true", help="Run one tip cycle then exit (default)")
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run forever: daily tips + Telegram commands + status heartbeats",
    )
    parser.add_argument("--json", action="store_true", help="Print selected tips as JSON")
    parser.add_argument(
        "--all-markets",
        action="store_true",
        help="Also print top analyzed markets before the filtered daily tips",
    )
    parser.add_argument("--demo", action="store_true", help="Force demo fixtures (no API required)")
    parser.add_argument("--test-telegram", action="store_true", help="Send a Telegram test message")
    parser.add_argument("--status", action="store_true", help="Print / push bot status")
    parser.add_argument("--min-confidence", type=float, default=None, help="Override MIN_CONFIDENCE")
    parser.add_argument("--target-odds", type=float, default=None, help="Override TARGET_ODDS")
    args = parser.parse_args()
    setup_logging(settings.log_level)
    cfg = build_config(args)
    scanner = PredictionScanner(cfg)
    scanner.status.mode = "once"

    if args.test_telegram:
        ok = scanner.telegram.send(
            "✅ Football Safety Bot Telegram OK\n"
            f"Safety: conf ≥ {cfg.safety_min_confidence:.0f}% | odds ≈ {cfg.target_odds:.2f}\n"
            f"Max daily tips: {cfg.max_daily_tips}\n"
            f"Leagues: {', '.join(cfg.leagues)}\n"
            "Commands: /status /tips /safety /help"
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

    all_tips, _fixture_count = scanner.analyze_all()
    selected = scanner.select_safety(all_tips)

    if args.json:
        print(json.dumps([t.to_dict() for t in selected], indent=2))
        return 0

    if args.all_markets:
        # show broader filter too
        broad = select_daily_tips(
            all_tips,
            min_confidence=cfg.min_confidence,
            target_odds=cfg.target_odds,
            odds_tolerance=cfg.odds_tolerance,
            max_tips=20,
        )
        for tip in broad[:40]:
            p = tip.prediction
            print(
                f"{tip.fixture.league_code} | {tip.fixture.label} | {p.market_label} | "
                f"odds={p.display_odds:.2f} conf={p.confidence:.0f}% "
                f"p={p.probability * 100:.1f}%"
            )
        print("─" * 36)

    report = format_daily_report(
        selected,
        min_confidence=cfg.safety_min_confidence,
        target_odds=cfg.target_odds,
        title="🛡️ SAFETY 3-ODD DAILY TIPS",
    )
    scanner._cached_report = report
    scanner._cached_tips = selected
    scanner.status.mark_scan(
        fixtures=_fixture_count,
        predictions=len(all_tips),
        tips=len(selected),
        summary=report.split("─")[0][:120],
        ok=True,
    )
    print(report)
    if scanner.telegram.enabled:
        if scanner.telegram.send(report):
            scanner.status.mark_telegram_push()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
