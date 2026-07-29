"""Match analysis engine — builds market predictions with confidence scores."""

from __future__ import annotations

from src.analysis.poisson import (
    blend_form_adjustment,
    expected_goals,
    fair_odds,
    implied_prob,
    market_probabilities,
)
from src.leagues import MARKET_LABELS
from src.models import Fixture, MarketPrediction, TeamForm, Tip


def _default_form(name: str, team_id: int | str = "") -> TeamForm:
    return TeamForm(
        team_id=team_id or name,
        team_name=name,
        played=8,
        wins=3,
        draws=2,
        losses=3,
        goals_for=10,
        goals_against=10,
        home_played=4,
        home_gf=6,
        home_ga=5,
        away_played=4,
        away_gf=4,
        away_ga=5,
        recent_results=list("WDLWDL"),
    )


def resolve_form(
    fixture: Fixture,
    forms_by_id: dict[str, TeamForm],
    forms_by_name: dict[str, TeamForm],
) -> tuple[TeamForm, TeamForm]:
    home = forms_by_id.get(str(fixture.home_team_id)) or forms_by_name.get(fixture.home_team)
    away = forms_by_id.get(str(fixture.away_team_id)) or forms_by_name.get(fixture.away_team)
    if home is None:
        # fuzzy name match
        home = _fuzzy(fixture.home_team, forms_by_name) or _default_form(
            fixture.home_team, fixture.home_team_id
        )
    if away is None:
        away = _fuzzy(fixture.away_team, forms_by_name) or _default_form(
            fixture.away_team, fixture.away_team_id
        )
    return home, away


def _fuzzy(name: str, forms: dict[str, TeamForm]) -> TeamForm | None:
    needle = name.lower()
    for key, form in forms.items():
        if needle in key.lower() or key.lower() in needle:
            return form
    return None


def confidence_score(
    probability: float,
    home: TeamForm,
    away: TeamForm,
    market: str,
    edge: float,
    sample_ok: bool,
) -> float:
    """
    Composite 0–100 model-conviction score (not a guaranteed hit rate).

    For ≈3.0 odds markets the raw win probability is often ~30–40%. Confidence
    rewards form alignment, data quality, and value edge so only strong setups
    clear the default 70% alert threshold.
    """
    # P=0.33 → ~62, P=0.45 → ~68, P=0.55 → ~72
    base = 48.0 + probability * 42.0

    diff = home.form_score - away.form_score
    if market == "home_win" and diff > 0.12:
        base += 10
    elif market == "away_win" and diff < -0.12:
        base += 10
    elif market == "draw" and abs(diff) < 0.14:
        base += 9
    elif market in {"over_25", "over_35", "btts_yes"} and (home.avg_gf + away.avg_gf) >= 2.6:
        base += 9
    elif market == "away_or_draw" and diff <= 0.05:
        base += 7
    elif market == "home_or_draw" and diff >= -0.05:
        base += 7

    if edge >= 0.08:
        base += 10
    elif edge >= 0.04:
        base += 7
    elif edge >= 0.02:
        base += 4
    elif edge < -0.03:
        base -= 8

    if sample_ok:
        base += 5
    else:
        base -= 8

    if market in {"draw", "under_25"} and home.avg_ga <= 1.15 and away.avg_ga <= 1.15:
        base += 5

    if market in {"over_25", "btts_yes"} and home.avg_ga >= 1.15 and away.avg_ga >= 1.15:
        base += 5

    # Conviction floor for clearly favoured mid-odds markets
    if probability >= 0.42 and sample_ok:
        base += 3

    return float(max(0.0, min(99.0, round(base, 1))))


def analyze_fixture(
    fixture: Fixture,
    home: TeamForm,
    away: TeamForm,
    markets: list[str],
    book_odds: dict[str, float] | None = None,
    league_avg_gf: float = 1.35,
) -> list[MarketPrediction]:
    home_xg, away_xg = expected_goals(home, away, league_avg_gf)
    probs = market_probabilities(home_xg, away_xg)
    sample_ok = home.played >= 5 and away.played >= 5
    book_odds = book_odds or {}

    predictions: list[MarketPrediction] = []
    for market in markets:
        if market not in probs:
            continue
        raw_p = probs[market]
        p = blend_form_adjustment(raw_p, home, away, market)
        f_odds = fair_odds(p)
        b_odds = book_odds.get(market)
        if b_odds and b_odds > 1:
            edge = p - implied_prob(b_odds)
        else:
            # Without books: edge vs naive market prior (form-adjusted conviction)
            priors = {
                "home_win": 0.45,
                "draw": 0.27,
                "away_win": 0.28,
                "home_or_draw": 0.72,
                "away_or_draw": 0.55,
                "btts_yes": 0.51,
                "btts_no": 0.49,
                "over_25": 0.52,
                "under_25": 0.48,
                "over_35": 0.30,
                "under_35": 0.70,
            }
            edge = p - priors.get(market, 0.33)

        conf = confidence_score(p, home, away, market, edge, sample_ok)
        reasons = _reasons(home, away, market, home_xg, away_xg, p, conf)

        predictions.append(
            MarketPrediction(
                market=market,
                market_label=MARKET_LABELS.get(market, market),
                probability=p,
                fair_odds=f_odds,
                book_odds=b_odds,
                confidence=conf,
                edge=edge,
                reasons=reasons,
            )
        )
    return predictions


def _reasons(
    home: TeamForm,
    away: TeamForm,
    market: str,
    home_xg: float,
    away_xg: float,
    p: float,
    conf: float,
) -> list[str]:
    reasons = [
        f"xG model: {home.team_name} {home_xg:.2f} – {away_xg:.2f} {away.team_name}",
        f"Model probability {p * 100:.1f}% | confidence {conf:.0f}%",
        f"Form: {home.team_name} {''.join(home.recent_results[-5:]) or 'n/a'} "
        f"({home.form_score:.2f}) vs {away.team_name} {''.join(away.recent_results[-5:]) or 'n/a'} "
        f"({away.form_score:.2f})",
    ]
    if market == "draw":
        reasons.append("Closely matched sides / balanced attack-defence profile favours X")
    elif market == "away_win":
        reasons.append(f"Away edge: {away.team_name} form/attack vs {home.team_name} home defence")
    elif market == "over_25":
        reasons.append(
            f"Combined scoring rate ~{home.avg_gf + away.avg_gf:.1f} GF/game supports Over 2.5"
        )
    elif market == "btts_yes":
        reasons.append("Both attacks average enough threat for BTTS Yes")
    elif market == "away_or_draw":
        reasons.append("Double chance X2 — away side competitive enough to avoid defeat")
    elif market == "over_35":
        reasons.append("High expected total goals supports Over 3.5")
    return reasons


def tips_from_predictions(fixture: Fixture, predictions: list[MarketPrediction]) -> list[Tip]:
    return [
        Tip(fixture=fixture, prediction=pred, rank_score=pred.confidence)
        for pred in predictions
    ]
