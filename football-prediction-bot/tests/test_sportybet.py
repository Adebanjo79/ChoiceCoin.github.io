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
    from src.daily_board import DailyBoard, format_daily_odds_report
    from src.sportybet import SportyBetBooking

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
        sportybet_code="ZZ9K21",
        sportybet_url="https://www.sportybet.com/ng/?shareCode=ZZ9K21",
    )
    board = DailyBoard(
        fixtures=[fixture],
        tips_3=[tip],
        tips_5=[],
        tips_50=[],
        day_label="Mon 03 Aug 2026",
        band_codes={
            "3odd": SportyBetBooking(
                share_code="BAND3X",
                share_url="https://www.sportybet.com/ng/?shareCode=BAND3X",
                matched=1,
            )
        },
    )
    report = format_daily_odds_report(board, Settings())
    assert "SportyBet code: ZZ9K21" in report
    assert "SportyBet BOOKING CODE: BAND3X" in report
    assert "sportybet.com" in report
