"""Core unit tests for Poisson model, confidence filter, and tip selection."""

from __future__ import annotations

from datetime import datetime, timezone

from src.analysis.engine import analyze_fixture, confidence_score
from src.analysis.poisson import expected_goals, fair_odds, market_probabilities
from src.models import Fixture, MarketPrediction, TeamForm, Tip
from src.selector import select_daily_tips


def _form(
    name: str,
    *,
    wins: int = 5,
    draws: int = 2,
    losses: int = 3,
    gf: int = 15,
    ga: int = 12,
    recent: str = "WWDLW",
) -> TeamForm:
    played = wins + draws + losses
    return TeamForm(
        team_id=name,
        team_name=name,
        played=played,
        wins=wins,
        draws=draws,
        losses=losses,
        goals_for=gf,
        goals_against=ga,
        home_played=max(1, played // 2),
        home_gf=gf // 2 + 1,
        home_ga=ga // 2,
        away_played=max(1, played - played // 2),
        away_gf=gf // 2,
        away_ga=ga // 2 + 1,
        recent_results=list(recent),
    )


def test_poisson_probabilities_sum_to_one():
    probs = market_probabilities(1.5, 1.2)
    total_1x2 = probs["home_win"] + probs["draw"] + probs["away_win"]
    assert 0.98 <= total_1x2 <= 1.02
    assert 0 <= probs["over_25"] <= 1
    assert abs(probs["btts_yes"] + probs["btts_no"] - 1.0) < 0.02


def test_fair_odds_inverse():
    assert abs(fair_odds(0.5) - 2.0) < 1e-9
    assert fair_odds(0.33) > 2.9


def test_expected_goals_home_advantage():
    home = _form("Home", wins=6, gf=18, ga=10)
    away = _form("Away", wins=6, gf=18, ga=10)
    hx, ax = expected_goals(home, away)
    assert hx > ax


def test_confidence_can_reach_seventy():
    home = _form("Strong", wins=8, draws=1, losses=1, gf=24, ga=8, recent="WWWWW")
    away = _form("Weak", wins=2, draws=2, losses=6, gf=8, ga=20, recent="LLLLD")
    conf = confidence_score(
        probability=0.48,
        home=home,
        away=away,
        market="home_win",
        edge=0.09,
        sample_ok=True,
    )
    assert conf >= 70


def test_analyze_fixture_returns_requested_markets():
    fixture = Fixture(
        id="1",
        league_code="PL",
        league_name="Premier League",
        kickoff=datetime.now(timezone.utc),
        home_team="Arsenal",
        away_team="Chelsea",
    )
    home = _form("Arsenal", wins=7, gf=22, ga=8, recent="WWWDW")
    away = _form("Chelsea", wins=4, gf=14, ga=14, recent="WDLLW")
    preds = analyze_fixture(
        fixture,
        home,
        away,
        markets=["draw", "away_win", "over_25", "btts_yes"],
        include_correct_scores=False,
    )
    keys = {p.market for p in preds}
    assert {"draw", "away_win", "over_25", "btts_yes"}.issubset(keys)
    assert all(1 < p.fair_odds < 80 for p in preds)


def test_select_daily_tips_filters_odds_and_confidence():
    fixture_a = Fixture(
        id="a",
        league_code="PL",
        league_name="Premier League",
        kickoff=datetime.now(timezone.utc),
        home_team="A",
        away_team="B",
    )
    fixture_b = Fixture(
        id="b",
        league_code="PD",
        league_name="La Liga",
        kickoff=datetime.now(timezone.utc),
        home_team="C",
        away_team="D",
    )
    tips = [
        Tip(
            fixture_a,
            MarketPrediction(
                market="draw",
                market_label="Draw",
                probability=0.34,
                fair_odds=3.0,
                book_odds=3.1,
                confidence=78,
                edge=0.05,
            ),
        ),
        Tip(
            fixture_a,
            MarketPrediction(
                market="over_25",
                market_label="Over 2.5",
                probability=0.55,
                fair_odds=1.8,
                book_odds=1.85,
                confidence=80,
                edge=0.02,
            ),
        ),
        Tip(
            fixture_b,
            MarketPrediction(
                market="away_win",
                market_label="Away Win",
                probability=0.33,
                fair_odds=3.05,
                book_odds=2.95,
                confidence=72,
                edge=0.04,
            ),
        ),
        Tip(
            fixture_b,
            MarketPrediction(
                market="draw",
                market_label="Draw",
                probability=0.30,
                fair_odds=3.3,
                book_odds=3.2,
                confidence=60,
                edge=0.01,
            ),
        ),
    ]
    selected = select_daily_tips(
        tips,
        min_confidence=70,
        target_odds=3.0,
        odds_tolerance=0.75,
        max_tips=5,
    )
    assert len(selected) == 2
    assert all(t.prediction.confidence >= 70 for t in selected)
    assert all(2.25 <= t.prediction.display_odds <= 3.75 for t in selected)
    # one tip per fixture
    assert len({t.fixture.id for t in selected}) == 2
