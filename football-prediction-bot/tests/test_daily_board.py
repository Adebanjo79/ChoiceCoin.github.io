"""Daily board formatting tests."""

from __future__ import annotations

from datetime import datetime, timezone

from config import Settings
from src.daily_board import build_daily_board, format_daily_odds_report
from src.models import Fixture, MarketPrediction, Tip


def test_daily_board_includes_dates():
    kick = datetime(2026, 8, 3, 15, 0, tzinfo=timezone.utc)
    fixture = Fixture(
        id="1",
        league_code="PL",
        league_name="Premier League",
        kickoff=kick,
        home_team="A",
        away_team="B",
    )
    tip = Tip(
        fixture,
        MarketPrediction(
            market="draw",
            market_label="Draw (X)",
            probability=0.34,
            fair_odds=3.0,
            book_odds=3.05,
            confidence=80,
            edge=0.05,
        ),
    )
    settings = Settings()
    board = build_daily_board([fixture], [tip], settings)
    report = format_daily_odds_report(board, settings)
    assert "DAILY FIXTURE ODDS" in report
    assert "Date:" in report
    assert "≈3.0" in report
    assert "≈5.0" in report
    assert "≈50" in report
