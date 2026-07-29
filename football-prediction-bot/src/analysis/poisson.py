"""Dixon-Coles-style independent Poisson match model."""

from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

from src.models import TeamForm


def _poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam**k) / math.factorial(k)


@lru_cache(maxsize=256)
def score_matrix(home_xg: float, away_xg: float, max_goals: int = 8) -> tuple[tuple[float, ...], ...]:
    """Return P(home_goals=i, away_goals=j) matrix as nested tuples (cacheable)."""
    home_xg = max(0.15, float(home_xg))
    away_xg = max(0.15, float(away_xg))
    matrix = []
    for i in range(max_goals + 1):
        row = []
        for j in range(max_goals + 1):
            row.append(_poisson_pmf(i, home_xg) * _poisson_pmf(j, away_xg))
        matrix.append(tuple(row))
    # renormalize truncated tail
    total = sum(sum(r) for r in matrix)
    if total <= 0:
        return tuple(matrix)
    return tuple(tuple(p / total for p in row) for row in matrix)


def expected_goals(home: TeamForm, away: TeamForm, league_avg_gf: float = 1.35) -> tuple[float, float]:
    """
    Attack/defence strength → expected goals.
    Home advantage baked in via home/away splits when available.
    """
    league_avg_gf = max(0.8, league_avg_gf)

    home_attack = home.home_avg_gf / league_avg_gf if home.home_played else home.avg_gf / league_avg_gf
    home_defence = home.home_avg_ga / league_avg_gf if home.home_played else home.avg_ga / league_avg_gf
    away_attack = away.away_avg_gf / league_avg_gf if away.away_played else away.avg_gf / league_avg_gf
    away_defence = away.away_avg_ga / league_avg_gf if away.away_played else away.avg_ga / league_avg_gf

    # Mild regression to mean for small samples
    shrink = 0.25
    home_attack = 1 + (home_attack - 1) * (1 - shrink)
    home_defence = 1 + (home_defence - 1) * (1 - shrink)
    away_attack = 1 + (away_attack - 1) * (1 - shrink)
    away_defence = 1 + (away_defence - 1) * (1 - shrink)

    home_xg = max(0.2, league_avg_gf * home_attack * away_defence * 1.08)  # home bump
    away_xg = max(0.2, league_avg_gf * away_attack * home_defence * 0.95)
    return home_xg, away_xg


def market_probabilities(home_xg: float, away_xg: float) -> dict[str, float]:
    matrix = score_matrix(round(home_xg, 3), round(away_xg, 3))
    n = len(matrix)
    home_win = draw = away_win = btts_yes = over_25 = over_35 = 0.0
    for i in range(n):
        for j in range(n):
            p = matrix[i][j]
            if i > j:
                home_win += p
            elif i == j:
                draw += p
            else:
                away_win += p
            if i > 0 and j > 0:
                btts_yes += p
            total = i + j
            if total > 2.5:
                over_25 += p
            if total > 3.5:
                over_35 += p

    return {
        "home_win": home_win,
        "draw": draw,
        "away_win": away_win,
        "home_or_draw": home_win + draw,
        "away_or_draw": away_win + draw,
        "btts_yes": btts_yes,
        "btts_no": 1.0 - btts_yes,
        "over_25": over_25,
        "under_25": 1.0 - over_25,
        "over_35": over_35,
        "under_35": 1.0 - over_35,
    }


def fair_odds(probability: float) -> float:
    p = min(max(probability, 0.01), 0.99)
    return 1.0 / p


def implied_prob(odds: float) -> float:
    return 1.0 / odds if odds and odds > 1 else 0.0


def blend_form_adjustment(base_prob: float, home: TeamForm, away: TeamForm, market: str) -> float:
    """Nudge 1X2 / BTTS probabilities using recent form differential."""
    diff = home.form_score - away.form_score  # positive => home in better form
    adj = 0.0
    if market == "home_win":
        adj = 0.06 * diff
    elif market == "away_win":
        adj = -0.06 * diff
    elif market == "draw":
        # Draws likelier when forms are close and both solid defensively
        closeness = 1.0 - abs(diff)
        defensive = 1.0 - min(1.0, (home.avg_gf + away.avg_gf) / 4.0)
        adj = 0.04 * closeness * (0.5 + 0.5 * defensive) - 0.02 * abs(diff)
    elif market == "btts_yes":
        attack = (home.avg_gf + away.avg_gf) / 4.0
        adj = 0.05 * (attack - 0.5)
    elif market in {"over_25", "over_35"}:
        attack = (home.avg_gf + away.avg_gf) / 4.0
        adj = 0.06 * (attack - 0.55)
    elif market == "away_or_draw":
        adj = -0.04 * diff
    elif market == "home_or_draw":
        adj = 0.04 * diff

    return float(np.clip(base_prob + adj, 0.02, 0.95))
