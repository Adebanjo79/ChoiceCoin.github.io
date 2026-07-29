"""Select daily tips near target odds with minimum confidence."""

from __future__ import annotations

from src.models import Tip


def select_daily_tips(
    tips: list[Tip],
    *,
    min_confidence: float = 70.0,
    target_odds: float = 3.0,
    odds_tolerance: float = 0.75,
    max_tips: int = 5,
) -> list[Tip]:
    """
    Keep tips with confidence >= min_confidence and odds within
    [target_odds - tolerance, target_odds + tolerance], ranked by score.

    Ranking prefers: higher confidence, then closer to target odds, then higher edge.
    """
    low = max(1.01, target_odds - odds_tolerance)
    high = target_odds + odds_tolerance

    eligible: list[Tip] = []
    for tip in tips:
        if tip.prediction.confidence < min_confidence:
            continue
        odds = tip.prediction.display_odds
        if odds < low or odds > high:
            continue
        odds_proximity = 1.0 - min(1.0, abs(odds - target_odds) / max(odds_tolerance, 0.01))
        tip.rank_score = (
            tip.prediction.confidence
            + odds_proximity * 22.0
            + max(0.0, tip.prediction.edge) * 35.0
        )
        eligible.append(tip)

    eligible.sort(key=lambda t: t.rank_score, reverse=True)

    # Diversify: one market per fixture, limit league repeats and market-type spam
    chosen: list[Tip] = []
    seen_fixtures: set[str] = set()
    seen_leagues: dict[str, int] = {}
    seen_markets: dict[str, int] = {}
    for tip in eligible:
        fid = tip.fixture.id
        if fid in seen_fixtures:
            continue
        league = tip.fixture.league_code
        market = tip.prediction.market
        if seen_leagues.get(league, 0) >= 2:
            continue
        if seen_markets.get(market, 0) >= 2 and len(chosen) + 1 < max_tips:
            # keep room for other market types near 3.0
            continue
        chosen.append(tip)
        seen_fixtures.add(fid)
        seen_leagues[league] = seen_leagues.get(league, 0) + 1
        seen_markets[market] = seen_markets.get(market, 0) + 1
        if len(chosen) >= max_tips:
            break

    if len(chosen) < max_tips:
        for tip in eligible:
            if tip.fixture.id in seen_fixtures:
                continue
            chosen.append(tip)
            seen_fixtures.add(tip.fixture.id)
            if len(chosen) >= max_tips:
                break

    return chosen


def format_daily_report(tips: list[Tip], *, min_confidence: float, target_odds: float) -> str:
    lines = [
        "⚽ FOOTBALL DAILY TIPS",
        f"Filter: confidence ≥ {min_confidence:.0f}% | odds ≈ {target_odds:.2f}",
        f"Picks: {len(tips)}",
        "─" * 36,
    ]
    if not tips:
        lines.append("NO TIPS – WAIT FOR BETTER SETUPS.")
        lines.append("Try widening ODDS_TOLERANCE or lowering MIN_CONFIDENCE slightly.")
        return "\n".join(lines)

    for i, tip in enumerate(tips, start=1):
        p = tip.prediction
        f = tip.fixture
        kick = f.kickoff.strftime("%Y-%m-%d %H:%M UTC")
        lines.extend(
            [
                f"{i}. [{f.league_name}] {f.label}",
                f"   Kickoff: {kick}",
                f"   Pick: {p.market_label}",
                f"   Odds: {p.display_odds:.2f} | Confidence: {p.confidence:.0f}% "
                f"| Model P: {p.probability * 100:.1f}%",
                f"   Why: {p.reasons[0] if p.reasons else 'Model edge'}",
                "",
            ]
        )
    lines.append("Not betting advice. Stake only what you can afford to lose.")
    return "\n".join(lines)
