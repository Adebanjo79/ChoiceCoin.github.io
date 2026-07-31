"""Select best tips near target odds bands (3 / 5 / 50) with confidence."""

from __future__ import annotations

from dataclasses import dataclass

from src.models import Tip


@dataclass(frozen=True)
class OddsBand:
    key: str
    title: str
    target_odds: float
    tolerance: float
    min_confidence: float
    max_tips: int
    prefer_safety_markets: bool = False


# Prefer these for the best ~3.0 "safety" band
SAFETY_MARKET_BONUS = {
    "away_or_draw": 6.0,
    "home_or_draw": 6.0,
    "draw": 5.0,
    "under_25": 3.0,
    "btts_no": 2.0,
    "away_win": 2.0,
    "over_25": 1.0,
}


def select_best_for_band(
    tips: list[Tip],
    band: OddsBand,
) -> list[Tip]:
    """
    Pick the best tips for one odds band.

    Ranking = confidence + closeness to target odds + edge (+ safety market bonus).
    One tip per fixture; diversify leagues.
    """
    low = max(1.01, band.target_odds - band.tolerance)
    high = band.target_odds + band.tolerance

    eligible: list[Tip] = []
    for tip in tips:
        if tip.prediction.confidence < band.min_confidence:
            continue
        odds = tip.prediction.display_odds
        if odds < low or odds > high:
            continue
        # For ~50 band, prefer correct scores / longshot markets
        if band.key == "50odd" and not (
            tip.prediction.market.startswith("cs_")
            or tip.prediction.market in {"over_45", "away_win_nil", "home_win_nil"}
        ):
            # still allow if odds naturally land near 50
            pass

        proximity = 1.0 - min(1.0, abs(odds - band.target_odds) / max(band.tolerance, 0.01))
        market_bonus = 0.0
        if band.prefer_safety_markets:
            market_bonus = SAFETY_MARKET_BONUS.get(tip.prediction.market, 0.0)
        if band.key == "50odd" and tip.prediction.market.startswith("cs_"):
            market_bonus += 8.0
        if band.key == "5odd" and tip.prediction.market in {
            "away_win",
            "draw",
            "over_35",
            "home_win_nil",
            "away_win_nil",
            "over_45",
        }:
            market_bonus += 4.0

        # Stronger proximity weight so we truly source the *best* match to target odd
        tip.rank_score = (
            tip.prediction.confidence
            + proximity * 35.0
            + max(0.0, tip.prediction.edge) * 40.0
            + market_bonus
        )
        eligible.append(tip)

    eligible.sort(key=lambda t: t.rank_score, reverse=True)

    chosen: list[Tip] = []
    seen_fixtures: set[str] = set()
    seen_leagues: dict[str, int] = {}
    max_per_league = 1 if band.max_tips <= 3 else 2

    for tip in eligible:
        if tip.fixture.id in seen_fixtures:
            continue
        league = tip.fixture.league_code
        if seen_leagues.get(league, 0) >= max_per_league:
            continue
        chosen.append(tip)
        seen_fixtures.add(tip.fixture.id)
        seen_leagues[league] = seen_leagues.get(league, 0) + 1
        if len(chosen) >= band.max_tips:
            break

    if len(chosen) < band.max_tips:
        for tip in eligible:
            if tip.fixture.id in seen_fixtures:
                continue
            chosen.append(tip)
            seen_fixtures.add(tip.fixture.id)
            if len(chosen) >= band.max_tips:
                break
    return chosen


def select_daily_tips(
    tips: list[Tip],
    *,
    min_confidence: float = 70.0,
    target_odds: float = 3.0,
    odds_tolerance: float = 0.75,
    max_tips: int = 5,
) -> list[Tip]:
    band = OddsBand(
        key="custom",
        title="DAILY TIPS",
        target_odds=target_odds,
        tolerance=odds_tolerance,
        min_confidence=min_confidence,
        max_tips=max_tips,
    )
    return select_best_for_band(tips, band)


def select_safety_tips(
    tips: list[Tip],
    *,
    min_confidence: float = 75.0,
    target_odds: float = 3.0,
    odds_tolerance: float = 0.75,
    max_tips: int = 3,
) -> list[Tip]:
    band = OddsBand(
        key="3odd",
        title="BEST 3-ODD",
        target_odds=target_odds,
        tolerance=odds_tolerance,
        min_confidence=min_confidence,
        max_tips=max_tips,
        prefer_safety_markets=True,
    )
    return select_best_for_band(tips, band)


def format_daily_report(
    tips: list[Tip],
    *,
    min_confidence: float,
    target_odds: float,
    title: str = "⚽ FOOTBALL DAILY TIPS",
) -> str:
    lines = [
        title,
        f"Filter: confidence ≥ {min_confidence:.0f}% | odds ≈ {target_odds:.2f}",
        f"Picks: {len(tips)}",
        "─" * 36,
    ]
    if not tips:
        lines.append("NO TIPS – WAIT FOR BETTER SETUPS.")
        lines.append("Bot is running. Check /status anytime on Telegram.")
        return "\n".join(lines)

    for i, tip in enumerate(tips, start=1):
        p = tip.prediction
        f = tip.fixture
        lines.extend(
            [
                f"{i}. [{f.league_name}] {f.label}",
                f"   Date: {f.kickoff_str}",
                f"   Pick: {p.market_label}",
                f"   Odds: {p.display_odds:.2f} | Confidence: {p.confidence:.0f}% "
                f"| Model P: {p.probability * 100:.1f}%",
                f"   Why: {p.reasons[0] if p.reasons else 'Model edge'}",
                "",
            ]
        )
    lines.append("Not betting advice. Stake only what you can afford to lose.")
    return "\n".join(lines)


def format_multi_band_report(
    bands: dict[str, list[Tip]],
    band_meta: dict[str, OddsBand],
) -> str:
    lines = [
        "⚽ DAILY ODDS BOARD",
        "Best sourced tips for ≈3 / ≈5 / ≈50 odds",
        "─" * 36,
    ]
    order = ["3odd", "5odd", "50odd"]
    for key in order:
        tips = bands.get(key, [])
        meta = band_meta[key]
        lines.append("")
        lines.append(f"{meta.title}")
        lines.append(
            f"conf ≥ {meta.min_confidence:.0f}% | target ≈ {meta.target_odds:.1f} | picks {len(tips)}"
        )
        if not tips:
            lines.append("  (no qualifying tips)")
            continue
        for i, tip in enumerate(tips, start=1):
            p = tip.prediction
            f = tip.fixture
            lines.append(
                f"  {i}. [{f.league_code}] {f.home_team} vs {f.away_team}"
            )
            lines.append(f"     Date: {f.kickoff_str}")
            lines.append(
                f"     {p.market_label} @ {p.display_odds:.2f} | "
                f"Conf {p.confidence:.0f}% | P {p.probability * 100:.1f}%"
            )
    lines.append("")
    lines.append("Not betting advice. /3odd /5odd /50odd /status")
    return "\n".join(lines)


def short_tips_summary(tips: list[Tip]) -> str:
    if not tips:
        return "No tips selected."
    parts = []
    for tip in tips:
        p = tip.prediction
        parts.append(
            f"{tip.fixture.home_team} vs {tip.fixture.away_team}: "
            f"{p.market_label} @ {p.display_odds:.2f} ({p.confidence:.0f}%)"
        )
    return " | ".join(parts)
