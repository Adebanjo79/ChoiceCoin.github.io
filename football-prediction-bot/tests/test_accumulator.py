"""Tests for accumulator builder (1–3 / 4+ / 7+ legs)."""

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


def _safe_pool() -> list[Tip]:
    # Many short-priced high-confidence legs for multi building
    markets = ["home_or_draw", "home_win", "under_25", "over_25", "away_or_draw"]
    tips = []
    for i in range(1, 16):
        tips.append(
            _tip(
                str(i),
                ["PL", "PD", "BL1", "FL1", "SA"][i % 5],
                markets[i % len(markets)],
                1.25 + (i % 5) * 0.12,
                76 + (i % 8),
                prob=0.55 + (i % 5) * 0.04,
            )
        )
    # Also a single near 3.0
    tips.append(_tip("s3", "PL", "draw", 3.05, 80, prob=0.33))
    return tips


def test_safest_3odd_offers_one_two_three_game_accus():
    spec = AccaSpec(
        band_key="3odd",
        title="SAFEST 3",
        target_odds=3.0,
        tolerance=0.75,
        min_confidence=75,
        min_legs=1,
        max_legs=3,
        max_accus=3,
    )
    accus = build_accumulators(_safe_pool(), spec)
    assert accus
    leg_counts = {a.leg_count for a in accus}
    assert leg_counts & {1, 2, 3}
    assert all(a.min_confidence >= 75 for a in accus)


def test_5odd_requires_more_than_three_games():
    spec = AccaSpec(
        band_key="5odd",
        title="5 ODD",
        target_odds=5.0,
        tolerance=1.5,
        min_confidence=70,
        min_legs=4,
        max_legs=6,
        max_accus=2,
    )
    accus = build_accumulators(_safe_pool(), spec)
    assert accus
    assert all(a.leg_count >= 4 for a in accus)


def test_50odd_uses_seven_plus_games():
    spec = AccaSpec(
        band_key="50odd",
        title="50 ODD",
        target_odds=50.0,
        tolerance=25.0,
        min_confidence=60,
        min_legs=7,
        max_legs=12,
        max_accus=2,
        leg_odds_min=1.20,
        leg_odds_max=2.35,
    )
    accus = build_accumulators(_safe_pool(), spec)
    assert accus
    assert all(a.leg_count >= 7 for a in accus)
