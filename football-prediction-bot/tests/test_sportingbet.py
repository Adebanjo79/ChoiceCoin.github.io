"""Sportingbet code helper tests."""

from __future__ import annotations

from datetime import datetime, timezone

from src.models import Fixture, MarketPrediction, Tip
from src.sportingbet import sportingbet_code, sportingbet_selection


def test_sportingbet_codes_for_common_markets():
    assert sportingbet_selection("draw")[0] == "X"
    assert sportingbet_selection("over_25")[0] == "O2.5"
    assert sportingbet_selection("btts_yes")[0] == "GG"
    assert sportingbet_selection("cs_2_1")[0] == "CS2-1"


def test_sportingbet_slip_line():
    tip = Tip(
        Fixture(
            id="1",
            league_code="PL",
            league_name="Premier League",
            kickoff=datetime(2026, 8, 3, 15, 0, tzinfo=timezone.utc),
            home_team="Arsenal",
            away_team="Chelsea",
        ),
        MarketPrediction(
            market="draw",
            market_label="Draw (X)",
            probability=0.33,
            fair_odds=3.0,
            book_odds=3.05,
            confidence=80,
            edge=0.02,
        ),
    )
    slip = sportingbet_code(tip)
    assert slip.startswith("SB|")
    assert "|X|" in slip
    assert "@3.05" in slip
    assert "PL" in tip.to_dict()["sportingbet_slip"]
