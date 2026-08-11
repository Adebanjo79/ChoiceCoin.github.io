"""Accumulator builder — careful multi-match tickets toward ≈3 / ≈5 / ≈50."""

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
    "over_35",
}


@dataclass
class Accumulator:
    """Multi-game ticket targeting a combined odds band."""

    legs: list[Tip]
    band_key: str
    target_odds: float
    label: str = ""
    option_index: int = 1
    sportybet_code: str | None = None
    sportybet_url: str | None = None

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
        proximity = max(0.0, 1.0 - gap)
        # Prefer higher min confidence (weakest-leg safety) + sooner kickoffs
        soon = 0.0
        try:
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc)
            days = [
                max(0.0, (leg.fixture.kickoff - now).total_seconds() / 86400.0)
                for leg in self.legs
            ]
            soon = max(0.0, 10.0 - (sum(days) / len(days)))
        except Exception:  # noqa: BLE001
            soon = 0.0
        return (
            self.avg_confidence * 0.40
            + self.min_confidence * 0.35
            + proximity * 90.0
            - gap * 30.0
            + soon
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "band": self.band_key,
            "label": self.label,
            "option": self.option_index,
            "legs": self.leg_count,
            "combined_odds": round(self.combined_odds, 2),
            "avg_confidence": round(self.avg_confidence, 1),
            "min_confidence": round(self.min_confidence, 1),
            "combined_probability_pct": round(self.combined_probability * 100, 2),
            "sportybet_code": self.sportybet_code,
            "sportybet_url": self.sportybet_url,
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
    leg_odds_min: float = 1.20
    leg_odds_max: float = 2.40
    prefer_safe_markets: bool = True
    max_accus: int = 3  # how many ticket OPTIONS to return


def specs_from_settings(settings) -> dict[str, AccaSpec]:
    return {
        "3odd": AccaSpec(
            band_key="3odd",
            title="🛡️ ≈3.0 ODDS — 3 MATCHES",
            target_odds=settings.target_odds,
            tolerance=settings.odds_tolerance,
            min_confidence=settings.safety_min_confidence,
            min_legs=settings.acca3_min_legs,
            max_legs=settings.acca3_max_legs,
            leg_odds_min=settings.acca_leg_odds_min,
            leg_odds_max=settings.acca_leg_odds_max,
            prefer_safe_markets=True,
            max_accus=max(1, settings.acca3_options),
        ),
        "5odd": AccaSpec(
            band_key="5odd",
            title="🎯 ≈5.0 ODDS — 3–5 MATCHES",
            target_odds=settings.target_odds_5,
            tolerance=settings.odds_tolerance_5,
            min_confidence=settings.odd5_min_confidence,
            min_legs=settings.acca5_min_legs,
            max_legs=settings.acca5_max_legs,
            leg_odds_min=settings.acca_leg_odds_min,
            leg_odds_max=min(settings.acca_leg_odds_max + 0.25, 2.80),
            prefer_safe_markets=True,
            max_accus=max(1, settings.acca5_options),
        ),
        "50odd": AccaSpec(
            band_key="50odd",
            title="🚀 ≈50 ODDS — 5–15 MATCHES",
            target_odds=settings.target_odds_50,
            tolerance=settings.odds_tolerance_50,
            min_confidence=settings.odd50_min_confidence,
            min_legs=settings.acca50_min_legs,
            max_legs=settings.acca50_max_legs,
            leg_odds_min=settings.acca_leg_odds_min,
            leg_odds_max=min(settings.acca_leg_odds_max + 0.45, 3.20),
            prefer_safe_markets=True,
            max_accus=max(1, settings.acca50_options),
        ),
    }


def _leg_candidates(
    tips: list[Tip],
    *,
    min_confidence: float,
    odds_min: float,
    odds_max: float,
    prefer_safe: bool,
) -> list[Tip]:
    """One best leg per fixture — high confidence, no correct scores as legs."""
    by_fixture: dict[str, Tip] = {}
    for tip in tips:
        if tip.prediction.market.startswith("cs_"):
            continue
        if tip.prediction.confidence < min_confidence:
            continue
        odds = tip.prediction.display_odds
        if odds < odds_min or odds > odds_max:
            continue
        if prefer_safe and tip.prediction.market not in SAFE_LEG_MARKETS:
            continue
        bonus = 6.0 if tip.prediction.market in {
            "home_or_draw",
            "away_or_draw",
            "under_25",
            "btts_no",
            "home_win",
        } else 0.0
        tip.rank_score = (
            tip.prediction.confidence
            + bonus
            + tip.prediction.probability * 12
            + max(0.0, tip.prediction.edge) * 20
        )
        fid = tip.fixture.id
        prev = by_fixture.get(fid)
        if prev is None or tip.rank_score > prev.rank_score:
            by_fixture[fid] = tip
    return sorted(by_fixture.values(), key=lambda t: t.rank_score, reverse=True)


def _rank_for_size(pool: list[Tip], n: int, target: float) -> list[Tip]:
    ideal = max(1.05, target ** (1.0 / max(n, 1)))
    return sorted(
        pool,
        key=lambda t: -(
            t.prediction.confidence
            - abs(t.prediction.display_odds - ideal) * 20.0
            + t.prediction.probability * 10.0
            + max(0.0, t.prediction.edge) * 15.0
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
    if n <= 0 or len(pool) < n:
        return None
    ranked = _rank_for_size(pool, n, target)
    capped = ranked[: min(len(ranked), 18 if n <= 3 else 16 if n <= 6 else 14)]
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
        # Prefer diversified leagues
        leagues = [t.fixture.league_code for t in combo]
        league_penalty = max(0, len(leagues) - len(set(leagues))) * 4.0
        acc = Accumulator(
            legs=list(combo),
            band_key=band_key,
            target_odds=target,
            label=f"{title_prefix} · {n} games",
        )
        sc = acc.score(tolerance) - league_penalty
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
    if len(pool) < n:
        return None
    ranked = _rank_for_size(pool, n, target)
    # Diversify: take top conf but skip duplicate leagues when possible
    chosen: list[Tip] = []
    used_leagues: dict[str, int] = {}
    for tip in ranked:
        lg = tip.fixture.league_code
        if used_leagues.get(lg, 0) >= 2 and len(chosen) < n - 1:
            continue
        chosen.append(tip)
        used_leagues[lg] = used_leagues.get(lg, 0) + 1
        if len(chosen) >= n:
            break
    if len(chosen) < n:
        ids = {t.fixture.id for t in chosen}
        for tip in ranked:
            if tip.fixture.id in ids:
                continue
            chosen.append(tip)
            if len(chosen) >= n:
                break
    if len(chosen) < n:
        return None

    best = Accumulator(
        legs=chosen[:n],
        band_key=band_key,
        target_odds=target,
        label=f"{title_prefix} · {n} games",
    )
    best_score = best.score(tolerance)
    unused = [t for t in ranked if t.fixture.id not in {x.fixture.id for x in best.legs}]

    improved = True
    rounds = 0
    while improved and rounds < 80:
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
    Build multiple carefully selected ticket OPTIONS for a band.

    - 3odd: fixed 3 matches, several alternative options
    - 5odd: 3–5 matches, several options
    - 50odd: 5–15 matches, fewer options
    """
    pool = _leg_candidates(
        tips,
        min_confidence=spec.min_confidence,
        odds_min=spec.leg_odds_min,
        odds_max=spec.leg_odds_max,
        prefer_safe=spec.prefer_safe_markets,
    )
    if not pool:
        return []

    sizes = list(range(spec.min_legs, spec.max_legs + 1))
    if not sizes:
        return []

    # Prefer sizes that can naturally reach the target odds
    def size_fit(n: int) -> float:
        ideal = spec.target_odds ** (1.0 / n)
        mid = (spec.leg_odds_min + spec.leg_odds_max) / 2
        return -abs(ideal - mid)

    sizes = sorted(sizes, key=size_fit, reverse=True)

    results: list[Accumulator] = []
    blocked: set[str] = set()  # fixtures used in previous options (for diversity)

    # Round-robin over sizes to build distinct options
    attempts = 0
    size_idx = 0
    while len(results) < spec.max_accus and attempts < spec.max_accus * len(sizes) + 5:
        attempts += 1
        n = sizes[size_idx % len(sizes)]
        size_idx += 1
        available = [t for t in pool if t.fixture.id not in blocked]
        if len(available) < n:
            # Soften diversity: allow reuse of older options' fixtures if pool too small
            available = list(pool)
            if len(available) < n:
                continue
        acc = _best_combo(
            available,
            n,
            spec.target_odds,
            spec.tolerance,
            spec.band_key,
            spec.title,
        )
        if acc is None:
            continue
        # Reject near-duplicates (same fixture set)
        sig = tuple(sorted(leg.fixture.id for leg in acc.legs))
        if any(
            tuple(sorted(leg.fixture.id for leg in prev.legs)) == sig for prev in results
        ):
            # Force diversity by blocking one fixture and retrying once
            if acc.legs:
                blocked.add(acc.legs[0].fixture.id)
            continue
        # Soft quality gate: odds not wildly off target
        gap = abs(acc.combined_odds - spec.target_odds) / spec.target_odds
        if gap > 1.25 and len(results) > 0:
            for leg in acc.legs:
                blocked.add(leg.fixture.id)
            continue

        option_no = len(results) + 1
        acc.option_index = option_no
        acc.label = f"Option {option_no} · {acc.leg_count} matches"
        results.append(acc)
        for leg in acc.legs:
            blocked.add(leg.fixture.id)

    results.sort(key=lambda a: -a.score(spec.tolerance))
    for i, acc in enumerate(results, start=1):
        acc.option_index = i
        acc.label = f"Option {i} · {acc.leg_count} matches"
    return results


def format_accumulator_report(
    accus: dict[str, list[Accumulator]],
    specs: dict[str, AccaSpec],
    *,
    day_label: str = "",
    fixture_count: int = 0,
) -> str:
    lines = [
        "⚽ CAREFUL ACCA BOARD",
        f"Day: {day_label}" if day_label else "Daily multi-match tickets",
        f"Fixtures loaded: {fixture_count}" if fixture_count else "",
        "≈3.0 → 3 matches | ≈5.0 → 3–5 | ≈50 → 5–15",
        "Each option has confidence + SportyBet booking code",
        "─" * 36,
    ]
    lines = [ln for ln in lines if ln != ""]
    order = ["3odd", "5odd", "50odd"]
    for key in order:
        spec = specs[key]
        group = accus.get(key, [])
        lines.append("")
        lines.append(f"{spec.title}")
        lines.append(
            f"target ≈ {spec.target_odds:.1f} | legs {spec.min_legs}–{spec.max_legs} | "
            f"conf ≥ {spec.min_confidence:.0f}% | options {len(group)}"
        )
        if not group:
            lines.append("  (no qualifying ticket — try /safety later)")
            continue
        for acc in group:
            lines.append("")
            lines.append(
                f"  ▸ {acc.label} | Combined @{acc.combined_odds:.2f}"
            )
            lines.append(
                f"    Avg conf {acc.avg_confidence:.0f}% | "
                f"Min conf {acc.min_confidence:.0f}% | "
                f"Model hit≈{acc.combined_probability * 100:.1f}%"
            )
            if acc.sportybet_code:
                lines.append(f"    SportyBet CODE: {acc.sportybet_code}")
                if acc.sportybet_url:
                    lines.append(f"    Load: {acc.sportybet_url}")
            else:
                lines.append("    SportyBet CODE: (pending — refresh /safety)")
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
    lines.append("Not betting advice. Accumulators lose if ANY leg fails.")
    lines.append("Telegram: /tips /3odd /5odd /50odd /codes /safety")
    return "\n".join(lines)


def format_band_accus(accus: list[Accumulator], spec: AccaSpec) -> str:
    lines = [
        spec.title,
        f"Target combined odds ≈ {spec.target_odds:.1f}",
        f"Legs: {spec.min_legs}–{spec.max_legs} | conf ≥ {spec.min_confidence:.0f}%",
        f"Options: {len(accus)}",
        "─" * 36,
    ]
    if not accus:
        lines.append("NO TICKET – send /safety to refresh.")
        return "\n".join(lines)
    for acc in accus:
        lines.append("")
        lines.append(f"▸ {acc.label} | @{acc.combined_odds:.2f}")
        lines.append(
            f"  Avg conf {acc.avg_confidence:.0f}% | Min conf {acc.min_confidence:.0f}%"
        )
        if acc.sportybet_code:
            lines.append(f"  SportyBet CODE: {acc.sportybet_code}")
            if acc.sportybet_url:
                lines.append(f"  Load: {acc.sportybet_url}")
        for i, leg in enumerate(acc.legs, start=1):
            p = leg.prediction
            f = leg.fixture
            lines.append(f"  {i}. [{f.league_code}] {f.label}")
            lines.append(f"     Date: {f.kickoff_str}")
            lines.append(
                f"     {p.market_label} @{p.display_odds:.2f} (conf {p.confidence:.0f}%)"
            )
    lines.append("")
    lines.append("Paste SportyBet code → Betslip → Booking Code → Load.")
    lines.append("Not betting advice. One losing leg kills the ticket.")
    return "\n".join(lines)
