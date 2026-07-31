"""Match analysis engine — builds market predictions with confidence scores."""

from __future__ import annotations

from src.analysis.poisson import (
    blend_form_adjustment,
    correct_score_probabilities,
    expected_goals,
    fair_odds,
    implied_prob,
    market_probabilities,
)
from src.leagues import market_label
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
    Longshot/correct-score markets use a separate calibration.
    """
    if market.startswith("cs_"):
        return _correct_score_confidence(probability, home, away, market, sample_ok)

    base = 48.0 + probability * 42.0

    diff = home.form_score - away.form_score
    if market == "home_win" and diff > 0.12:
        base += 10
    elif market == "away_win" and diff < -0.12:
        base += 10
    elif market == "draw" and abs(diff) < 0.14:
        base += 9
    elif market in {"over_25", "over_35", "over_45", "btts_yes"} and (
        home.avg_gf + away.avg_gf
    ) >= 2.6:
        base += 9
    elif market == "away_or_draw" and diff <= 0.05:
        base += 7
    elif market == "home_or_draw" and diff >= -0.05:
        base += 7
    elif market == "home_win_nil" and diff > 0.1 and home.avg_ga <= 1.1:
        base += 8
    elif market == "away_win_nil" and diff < -0.1 and away.avg_ga <= 1.1:
        base += 8

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

    if probability >= 0.42 and sample_ok:
        base += 3

    return float(max(0.0, min(99.0, round(base, 1))))


def _correct_score_confidence(
    probability: float,
    home: TeamForm,
    away: TeamForm,
    market: str,
    sample_ok: bool,
) -> float:
    """Confidence among longshots — relative model preference, not hit-rate promise."""
    # p=0.02 → ~65, p=0.03 → ~80, p=0.01 → ~50
    base = 35.0 + min(45.0, probability * 1500.0)
    parts = market.split("_")
    hg = int(parts[1]) if len(parts) == 3 else 0
    ag = int(parts[2]) if len(parts) == 3 else 0
    diff = home.form_score - away.form_score
    if hg > ag and diff > 0.08:
        base += 10
    elif ag > hg and diff < -0.08:
        base += 10
    elif hg == ag and abs(diff) < 0.12:
        base += 8
    if hg + ag >= 4 and (home.avg_gf + away.avg_gf) >= 2.8:
        base += 4
    if sample_ok:
        base += 5
    else:
        base -= 6
    return float(max(0.0, min(95.0, round(base, 1))))


_PRIORS = {
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
    "over_45": 0.18,
    "home_win_nil": 0.22,
    "away_win_nil": 0.12,
}


def analyze_fixture(
    fixture: Fixture,
    home: TeamForm,
    away: TeamForm,
    markets: list[str],
    book_odds: dict[str, float] | None = None,
    league_avg_gf: float = 1.35,
    *,
    include_correct_scores: bool = True,
) -> list[MarketPrediction]:
    home_xg, away_xg = expected_goals(home, away, league_avg_gf)
    probs = market_probabilities(home_xg, away_xg)
    if include_correct_scores:
        probs.update(correct_score_probabilities(home_xg, away_xg, max_goals=5))

    # Always analyze configured markets + high-odds helpers when present in probs
    wanted = set(markets) | {
        "over_45",
        "home_win_nil",
        "away_win_nil",
    }
    if include_correct_scores:
        wanted |= {k for k in probs if k.startswith("cs_")}

    sample_ok = home.played >= 5 and away.played >= 5
    book_odds = book_odds or {}

    predictions: list[MarketPrediction] = []
    for market in sorted(wanted):
        if market not in probs:
            continue
        # Skip extremely tiny CS tails (noise)
        raw_p = probs[market]
        if market.startswith("cs_") and raw_p < 0.008:
            continue
        p = (
            raw_p
            if market.startswith("cs_")
            else blend_form_adjustment(raw_p, home, away, market)
        )
        f_odds = fair_odds(p)
        b_odds = book_odds.get(market)
        if b_odds and b_odds > 1:
            edge = p - implied_prob(b_odds)
        else:
            prior = _PRIORS.get(market, 0.02 if market.startswith("cs_") else 0.33)
            edge = p - prior

        conf = confidence_score(p, home, away, market, edge, sample_ok)
        reasons = _reasons(home, away, market, home_xg, away_xg, p, conf)

        predictions.append(
            MarketPrediction(
                market=market,
                market_label=market_label(market),
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
    if market.startswith("cs_"):
        reasons.append("Best-ranked correct score from Poisson matrix for this odds band")
    elif market == "draw":
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
    elif market in {"over_35", "over_45"}:
        reasons.append("High expected total goals supports this overs line")
    elif market in {"home_win_nil", "away_win_nil"}:
        reasons.append("Win-to-nil supported by attack edge + defensive profile")
    return reasons


def tips_from_predictions(fixture: Fixture, predictions: list[MarketPrediction]) -> list[Tip]:
    return [
        Tip(fixture=fixture, prediction=pred, rank_score=pred.confidence)
        for pred in predictions
    ]
