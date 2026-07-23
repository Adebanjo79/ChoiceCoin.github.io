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
    args = parser.parse_args()
    setup_logging(settings.log_level)

    scanner = MarketScanner(settings)

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
