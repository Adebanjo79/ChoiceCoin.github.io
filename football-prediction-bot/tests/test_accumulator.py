"""Tests for careful multi-match accumulator builder."""

from __future__ import annotations

from datetime import datetime, timezone

from src.accumulator import AccaSpec, build_accumulators
from src.models import Fixture, MarketPrediction, Tip


def _tip(fid: str, league: str, market: str, odds: float, conf: float, prob: float | None = None) -> Tip:
    p = prob if prob is not None else min(0.85, 1 / odds)
    return Tip(
        Fixture(
            id=fid,
            league_code=league,
            league_name=league,
            kickoff=datetime.now(timezone.utc),
            home_team=f"Home{fid}",
            away_team=f"Away{fid}",
        ),
        MarketPrediction(
            market=market,
            market_label=market,
            probability=p,
            fair_odds=odds,
            book_odds=odds,
            confidence=conf,
            edge=0.05,
        ),
    )


def _safe_pool(n: int = 20) -> list[Tip]:
    markets = ["home_or_draw", "home_win", "under_25", "over_25", "away_or_draw", "btts_no"]
    tips = []
    leagues = ["PL", "PD", "BL1", "FL1", "SA", "ELC", "DED"]
    for i in range(1, n + 1):
        tips.append(
            _tip(
                str(i),
                leagues[i % len(leagues)],
                markets[i % len(markets)],
                1.25 + (i % 6) * 0.12,
                76 + (i % 8),
                prob=0.55 + (i % 5) * 0.04,
            )
        )
    return tips


def test_3odd_builds_three_match_options():
    spec = AccaSpec(
        band_key="3odd",
        title="≈3",
        target_odds=3.0,
        tolerance=0.9,
        min_confidence=75,
        min_legs=3,
        max_legs=3,
        max_accus=3,
    )
    accus = build_accumulators(_safe_pool(), spec)
    assert accus
    assert all(a.leg_count == 3 for a in accus)
    assert all(a.min_confidence >= 75 for a in accus)
    assert len(accus) >= 1
    # Options should be diversely labeled
    assert accus[0].label.startswith("Option")


def test_5odd_uses_3_to_5_matches_with_options():
    spec = AccaSpec(
        band_key="5odd",
        title="≈5",
        target_odds=5.0,
        tolerance=1.5,
        min_confidence=70,
        min_legs=3,
        max_legs=5,
        max_accus=3,
    )
    accus = build_accumulators(_safe_pool(), spec)
    assert accus
    assert all(3 <= a.leg_count <= 5 for a in accus)
    assert len(accus) >= 1


def test_50odd_uses_5_to_15_matches():
    spec = AccaSpec(
        band_key="50odd",
        title="≈50",
        target_odds=50.0,
        tolerance=25.0,
        min_confidence=60,
        min_legs=5,
        max_legs=15,
        max_accus=2,
        leg_odds_min=1.20,
        leg_odds_max=2.50,
    )
    accus = build_accumulators(_safe_pool(24), spec)
    assert accus
    assert all(5 <= a.leg_count <= 15 for a in accus)
