"""Accumulator (acca) builder — combine safest legs toward target odds."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from math import prod
from typing import Any

from src.models import Tip

# Safer shorter-priced markets preferred as acca legs
SAFE_LEG_MARKETS = {
    "home_win",
    "home_or_draw",
    "away_or_draw",
    "under_25",
    "btts_no",
    "over_25",
    "draw",
    "away_win",
    "btts_yes",
}


@dataclass
class Accumulator:
    """Multi-game ticket targeting a combined odds band."""

    legs: list[Tip]
    band_key: str
    target_odds: float
    label: str = ""

    @property
    def combined_odds(self) -> float:
        if not self.legs:
            return 0.0
        return float(prod(leg.prediction.display_odds for leg in self.legs))

    @property
    def avg_confidence(self) -> float:
        if not self.legs:
            return 0.0
        return sum(leg.prediction.confidence for leg in self.legs) / len(self.legs)

    @property
    def min_confidence(self) -> float:
        if not self.legs:
            return 0.0
        return min(leg.prediction.confidence for leg in self.legs)

    @property
    def combined_probability(self) -> float:
        if not self.legs:
            return 0.0
        p = 1.0
        for leg in self.legs:
            p *= max(0.01, min(0.99, leg.prediction.probability))
        return p

    @property
    def leg_count(self) -> int:
        return len(self.legs)

    def score(self, tolerance: float) -> float:
        """Higher is better: confidence + closeness to target combined odds."""
        if not self.legs or self.target_odds <= 0:
            return -1e9
        gap = abs(self.combined_odds - self.target_odds) / self.target_odds
        # Soft proximity — still rewards getting nearer even outside tolerance
        proximity = max(0.0, 1.0 - gap)
        # Prefer higher min confidence (weakest-leg safety)
        return (
            self.avg_confidence * 0.35
            + self.min_confidence * 0.25
            + proximity * 80.0
            - gap * 25.0
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "band": self.band_key,
            "label": self.label,
            "legs": self.leg_count,
            "combined_odds": round(self.combined_odds, 2),
            "avg_confidence": round(self.avg_confidence, 1),
            "min_confidence": round(self.min_confidence, 1),
            "combined_probability_pct": round(self.combined_probability * 100, 2),
            "selections": [leg.to_dict() for leg in self.legs],
        }


@dataclass(frozen=True)
class AccaSpec:
    band_key: str
    title: str
    target_odds: float
    tolerance: float
    min_confidence: float
    min_legs: int
    max_legs: int
    # Individual leg odds window (safer shorter prices for multi legs)
    leg_odds_min: float = 1.20
    leg_odds_max: float = 2.40
    prefer_safe_markets: bool = True
    max_accus: int = 3  # how many acca options to return (e.g. 1-leg, 2-leg, 3-leg)


def _leg_candidates(
    tips: list[Tip],
    *,
    min_confidence: float,
    odds_min: float,
    odds_max: float,
    prefer_safe: bool,
) -> list[Tip]:
    """One best leg per fixture, high confidence, usable as acca building blocks."""
    by_fixture: dict[str, Tip] = {}
    for tip in tips:
        if tip.prediction.confidence < min_confidence:
            continue
        odds = tip.prediction.display_odds
        if odds < odds_min or odds > odds_max:
            continue
        if prefer_safe and tip.prediction.market.startswith("cs_"):
            continue
        if prefer_safe and tip.prediction.market not in SAFE_LEG_MARKETS:
            # allow home_win etc. already in set; skip exotic longshots as legs
            if tip.prediction.market not in {
                "home_win",
                "away_win",
                "draw",
                "home_or_draw",
                "away_or_draw",
                "over_25",
                "under_25",
                "btts_yes",
                "btts_no",
                "over_35",
            }:
                continue
        bonus = 5.0 if tip.prediction.market in SAFE_LEG_MARKETS else 0.0
        tip.rank_score = tip.prediction.confidence + bonus + tip.prediction.probability * 10
        fid = tip.fixture.id
        prev = by_fixture.get(fid)
        if prev is None or tip.rank_score > prev.rank_score:
            by_fixture[fid] = tip
    legs = sorted(by_fixture.values(), key=lambda t: t.rank_score, reverse=True)
    return legs


def _rank_for_size(pool: list[Tip], n: int, target: float) -> list[Tip]:
    """Prefer legs near geometric mean odds needed for n-leg target."""
    ideal = max(1.05, target ** (1.0 / max(n, 1)))
    return sorted(
        pool,
        key=lambda t: -(
            t.prediction.confidence
            - abs(t.prediction.display_odds - ideal) * 18.0
            + t.prediction.probability * 8.0
        ),
    )


def _best_combo(
    pool: list[Tip],
    n: int,
    target: float,
    tolerance: float,
    band_key: str,
    title_prefix: str,
) -> Accumulator | None:
    """Search combinations of size n; cap pool for speed."""
    if n <= 0 or len(pool) < n:
        return None
    ranked = _rank_for_size(pool, n, target)
    capped = ranked[: min(len(ranked), 16 if n <= 3 else 14 if n <= 6 else 12)]
    best: Accumulator | None = None
    best_score = -1e9

    if n == 1:
        for tip in capped:
            acc = Accumulator(
                legs=[tip],
                band_key=band_key,
                target_odds=target,
                label=f"{title_prefix} · 1 game",
            )
            sc = acc.score(tolerance)
            if sc > best_score:
                best_score = sc
                best = acc
        return best

    if n >= 4 or len(capped) > 12:
        return _greedy_acca(ranked, n, target, tolerance, band_key, title_prefix)

    for combo in combinations(capped, n):
        acc = Accumulator(
            legs=list(combo),
            band_key=band_key,
            target_odds=target,
            label=f"{title_prefix} · {n} games",
        )
        sc = acc.score(tolerance)
        if sc > best_score:
            best_score = sc
            best = acc
    return best


def _greedy_acca(
    pool: list[Tip],
    n: int,
    target: float,
    tolerance: float,
    band_key: str,
    title_prefix: str,
) -> Accumulator | None:
    """Build n-leg acca close to target odds using confidence + ideal price."""
    if len(pool) < n:
        return None
    ranked = _rank_for_size(pool, n, target)
    chosen = list(ranked[:n])
    best = Accumulator(
        legs=chosen,
        band_key=band_key,
        target_odds=target,
        label=f"{title_prefix} · {n} games",
    )
    best_score = best.score(tolerance)
    unused = ranked[n:]

    improved = True
    rounds = 0
    while improved and rounds < 60:
        improved = False
        rounds += 1
        for i, leg in enumerate(list(best.legs)):
            for cand in unused:
                trial_legs = list(best.legs)
                trial_legs[i] = cand
                fids = [t.fixture.id for t in trial_legs]
                if len(set(fids)) != len(fids):
                    continue
                trial = Accumulator(
                    legs=trial_legs,
                    band_key=band_key,
                    target_odds=target,
                    label=f"{title_prefix} · {n} games",
                )
                sc = trial.score(tolerance)
                if sc > best_score + 0.01:
                    unused = [u for u in unused if u.fixture.id != cand.fixture.id] + [leg]
                    best = trial
                    best_score = sc
                    improved = True
                    break
            if improved:
                break
    return best

def build_accumulators(tips: list[Tip], spec: AccaSpec) -> list[Accumulator]:
    """
    Build 1..N accumulator options for a band.

    For 3-odd safety: typically returns best 1-game, 2-game, and 3-game tickets
    each aiming near target combined odds.
    For 5-odd / 50-odd: returns tickets with min_legs..max_legs (more games).
    """
    pool = _leg_candidates(
        tips,
        min_confidence=spec.min_confidence,
        odds_min=spec.leg_odds_min,
        odds_max=spec.leg_odds_max,
        prefer_safe=spec.prefer_safe_markets,
    )
    # Singles pool can use higher individual odds near the band target
    singles_pool = _leg_candidates(
        tips,
        min_confidence=spec.min_confidence,
        odds_min=max(1.01, spec.target_odds - spec.tolerance),
        odds_max=spec.target_odds + spec.tolerance,
        prefer_safe=spec.prefer_safe_markets,
    )

    results: list[Accumulator] = []
    sizes = list(range(spec.min_legs, spec.max_legs + 1))
    if spec.band_key == "50odd":
        # Prefer larger folds first so combined odds can reach ≈50
        sizes = sorted(sizes, reverse=True)
    if spec.band_key in {"5odd", "50odd"} and len(sizes) > spec.max_accus:
        step = max(1, len(sizes) // spec.max_accus)
        picked = sizes[::step][: spec.max_accus]
        if spec.band_key == "50odd" and spec.max_legs not in picked:
            picked[-1] = spec.max_legs
        elif spec.band_key == "5odd" and sizes and picked[-1] != spec.max_legs:
            picked[-1] = spec.max_legs
        sizes = picked

    for n in sizes:
        use_pool = singles_pool if n == 1 else pool
        if not use_pool:
            continue
        acc = _best_combo(
            use_pool,
            n,
            spec.target_odds,
            spec.tolerance,
            spec.band_key,
            spec.title,
        )
        if acc is None:
            continue
        results.append(acc)
        if len(results) >= spec.max_accus and spec.band_key != "3odd":
            break

    # For 3-odd keep one option per leg count (1,2,3) sorted by score within size
    if spec.band_key == "3odd":
        by_n: dict[int, Accumulator] = {}
        for acc in results:
            prev = by_n.get(acc.leg_count)
            if prev is None or acc.score(spec.tolerance) > prev.score(spec.tolerance):
                by_n[acc.leg_count] = acc
        results = [by_n[n] for n in sorted(by_n)]
    else:
        results.sort(key=lambda a: -a.score(spec.tolerance))
        results = results[: spec.max_accus]
    return results


def format_accumulator_report(
    accus: dict[str, list[Accumulator]],
    specs: dict[str, AccaSpec],
) -> str:
    lines = [
        "⚽ DAILY ACCA BOARD",
        "Safest multi-game tickets → ≈3 / ≈5 / ≈50 combined odds",
        "Fixtures window: next 3 days (see each leg date)",
        "─" * 36,
    ]
    order = ["3odd", "5odd", "50odd"]
    for key in order:
        spec = specs[key]
        group = accus.get(key, [])
        lines.append("")
        lines.append(f"{spec.title}")
        lines.append(
            f"target ≈ {spec.target_odds:.1f} | legs {spec.min_legs}–{spec.max_legs} | "
            f"conf ≥ {spec.min_confidence:.0f}%"
        )
        if not group:
            lines.append("  (no qualifying accumulator)")
            continue
        for acc in group:
            lines.append(
                f"  ▸ {acc.label} | Combined @{acc.combined_odds:.2f} | "
                f"Avg conf {acc.avg_confidence:.0f}% | Min conf {acc.min_confidence:.0f}%"
            )
            for i, leg in enumerate(acc.legs, start=1):
                p = leg.prediction
                f = leg.fixture
                lines.append(
                    f"     {i}. [{f.league_code}] {f.home_team} vs {f.away_team}"
                )
                lines.append(f"        Date: {f.kickoff_str}")
                lines.append(
                    f"        {p.market_label} @{p.display_odds:.2f} "
                    f"(conf {p.confidence:.0f}%)"
                )
    lines.append("")
    lines.append("Not betting advice. Accumulators lose if any leg fails.")
    lines.append("Telegram: /tips /3odd /5odd /50odd /status")
    return "\n".join(lines)


def format_band_accus(accus: list[Accumulator], spec: AccaSpec) -> str:
    lines = [
        spec.title,
        f"Target combined odds ≈ {spec.target_odds:.1f} (±{spec.tolerance:.1f})",
        f"Legs allowed: {spec.min_legs}–{spec.max_legs} | conf ≥ {spec.min_confidence:.0f}%",
        "Each fixture shows full date + kickoff (UTC)",
        "─" * 36,
    ]
    if not accus:
        lines.append("NO ACCA – WAIT FOR BETTER SETUPS.")
        return "\n".join(lines)
    for acc in accus:
        lines.append("")
        lines.append(
            f"▸ {acc.label} | @{acc.combined_odds:.2f} | "
            f"Avg {acc.avg_confidence:.0f}% | Min {acc.min_confidence:.0f}%"
        )
        for i, leg in enumerate(acc.legs, start=1):
            p = leg.prediction
            f = leg.fixture
            lines.append(f"  {i}. [{f.league_code}] {f.label}")
            lines.append(f"     Date: {f.kickoff_str}")
            lines.append(
                f"     {p.market_label} @{p.display_odds:.2f} (conf {p.confidence:.0f}%)"
            )
    lines.append("")
    lines.append("Not betting advice. One losing leg kills the accumulator.")
    return "\n".join(lines)
