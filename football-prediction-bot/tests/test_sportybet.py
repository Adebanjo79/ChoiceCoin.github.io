"""SportyBet booking code unit tests (no live network)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.models import Fixture, MarketPrediction, Tip
from src.sportybet import (
    MARKET_MAP,
    SportyBetBooking,
    SportyBetClient,
    market_selection,
)


def test_market_selection_common():
    assert market_selection("home_win") == ("1", "1", "")
    assert market_selection("draw") == ("1", "2", "")
    assert market_selection("over_25") == ("18", "12", "total=2.5")
    assert market_selection("btts_yes") == ("29", "74", "")
    assert market_selection("home_or_draw") == ("10", "9", "")
    assert market_selection("away_or_draw") == ("10", "11", "")
    assert market_selection("home_win_nil") == ("33", "74", "")


def test_correct_score_outcome_ids():
    assert market_selection("cs_0_0") == ("45", "274", "")
    assert market_selection("cs_2_1") == ("45", "288", "")
    assert market_selection("cs_4_4") == ("45", "322", "")
    assert market_selection("cs_5_0") is None  # out of SportyBet CS grid


def test_all_default_markets_mapped():
    for key in (
        "home_win",
        "draw",
        "away_win",
        "over_25",
        "under_25",
        "btts_yes",
        "btts_no",
        "away_or_draw",
        "home_or_draw",
        "over_35",
        "over_45",
        "home_win_nil",
        "away_win_nil",
    ):
        assert key in MARKET_MAP
        assert market_selection(key) is not None


def test_book_tip_attaches_code():
    tip = Tip(
        Fixture(
            id="1",
            league_code="PL",
            league_name="Premier League",
            kickoff=datetime(2026, 8, 15, 15, 0, tzinfo=timezone.utc),
            home_team="Man City",
            away_team="Bournemouth",
        ),
        MarketPrediction(
            market="home_win",
            market_label="Home Win",
            probability=0.55,
            fair_odds=1.8,
            book_odds=1.9,
            confidence=80,
            edge=0.05,
        ),
    )
    client = SportyBetClient()
    client.find_event = MagicMock(  # type: ignore[method-assign]
        return_value={"eventId": "sr:match:1", "homeTeamName": "Man City", "awayTeamName": "Bournemouth"}
    )
    client.create_booking = MagicMock(  # type: ignore[method-assign]
        return_value=SportyBetBooking(
            share_code="ABC123",
            share_url="https://www.sportybet.com/ng/?shareCode=ABC123",
            event_id="sr:match:1",
            matched=1,
        )
    )
    booking = client.book_tip(tip)
    assert booking is not None
    assert tip.sportybet_code == "ABC123"
    assert "shareCode=ABC123" in (tip.sportybet_url or "")
    assert tip.to_dict()["sportybet_code"] == "ABC123"


def test_daily_report_shows_sportybet_code():
    from config import Settings
    from src.accumulator import Accumulator, AccaSpec
    from src.daily_board import DailyBoard, format_daily_odds_report, format_sportybet_codes_report
    from src.sportybet import SportyBetBooking

    kick = datetime(2026, 8, 3, 15, 0, tzinfo=timezone.utc)
    tips = []
    for i in range(3):
        tips.append(
            Tip(
                Fixture(
                    id=str(i + 1),
                    league_code="PL",
                    league_name="Premier League",
                    kickoff=kick,
                    home_team=f"H{i}",
                    away_team=f"A{i}",
                ),
                MarketPrediction(
                    market="home_or_draw",
                    market_label="1X",
                    probability=0.6,
                    fair_odds=1.4,
                    book_odds=1.4,
                    confidence=80,
                    edge=0.05,
                ),
            )
        )
    acc = Accumulator(
        legs=tips,
        band_key="3odd",
        target_odds=3.0,
        label="Option 1 · 3 matches",
        option_index=1,
        sportybet_code="BAND3X",
        sportybet_url="https://www.sportybet.com/ng/?shareCode=BAND3X",
    )
    board = DailyBoard(
        fixtures=[tips[0].fixture],
        day_label="Mon 03 Aug 2026",
        accus={"3odd": [acc], "5odd": [], "50odd": []},
        specs={
            "3odd": AccaSpec("3odd", "≈3", 3.0, 0.75, 75, 3, 3),
            "5odd": AccaSpec("5odd", "≈5", 5.0, 1.25, 70, 3, 5),
            "50odd": AccaSpec("50odd", "≈50", 50.0, 20, 60, 5, 15),
        },
        tips_3=tips,
        band_codes={
            "3odd": SportyBetBooking(
                share_code="BAND3X",
                share_url="https://www.sportybet.com/ng/?shareCode=BAND3X",
                matched=3,
            )
        },
    )
    report = format_daily_odds_report(board, Settings())
    assert "BAND3X" in report
    assert "Option 1" in report
    assert "sportybet.com" in report
    codes = format_sportybet_codes_report(board)
    assert "CODE: BAND3X" in codes
