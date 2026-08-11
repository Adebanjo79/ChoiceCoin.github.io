"""Daily board formatting tests."""

from __future__ import annotations

from datetime import datetime, timezone

from config import Settings
from src.daily_board import build_daily_board, format_daily_odds_report
from src.models import Fixture, MarketPrediction, Tip


def _tip(i: int, league: str, market: str, odds: float, conf: float) -> Tip:
    return Tip(
        Fixture(
            id=str(i),
            league_code=league,
            league_name=league,
            kickoff=datetime(2026, 8, 15, 15, 0, tzinfo=timezone.utc),
            home_team=f"Home{i}",
            away_team=f"Away{i}",
        ),
        MarketPrediction(
            market=market,
            market_label=market,
            probability=min(0.8, 1 / odds),
            fair_odds=odds,
            book_odds=odds,
            confidence=conf,
            edge=0.05,
        ),
    )


def test_daily_board_builds_acca_options():
    leagues = ["PL", "PD", "BL1", "FL1", "SA", "ELC", "DED", "PPL"]
    markets = ["home_or_draw", "home_win", "under_25", "over_25", "away_or_draw", "btts_no"]
    tips = []
    fixtures = []
    for i in range(1, 18):
        tip = _tip(i, leagues[i % len(leagues)], markets[i % len(markets)], 1.3 + (i % 5) * 0.1, 78)
        tips.append(tip)
        fixtures.append(tip.fixture)
    settings = Settings()
    board = build_daily_board(fixtures, tips, settings)
    report = format_daily_odds_report(board, settings)
    assert "ACCA" in report or "≈3.0" in report
    assert "Option" in report or "no qualifying" in report.lower()
    assert "≈3.0" in report
    assert "≈5.0" in report
    assert "≈50" in report
    # 3-odd options should be 3 legs when built
    for acc in board.accus.get("3odd", []):
        assert acc.leg_count == 3
