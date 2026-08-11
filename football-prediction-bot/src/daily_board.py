"""Daily careful acca board — multi-match ≈3 / ≈5 / ≈50 options + SportyBet codes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.accumulator import (
    AccaSpec,
    Accumulator,
    build_accumulators,
    format_accumulator_report,
    format_band_accus,
    specs_from_settings,
)
from src.models import Fixture, Tip
from src.sportybet import SportyBetBooking


@dataclass
class DailyBoard:
    fixtures: list[Fixture]
    day_label: str
    accus: dict[str, list[Accumulator]] = field(default_factory=dict)
    specs: dict[str, AccaSpec] = field(default_factory=dict)
    # Compatibility: first option legs as tip lists
    tips_3: list[Tip] = field(default_factory=list)
    tips_5: list[Tip] = field(default_factory=list)
    tips_50: list[Tip] = field(default_factory=list)
    band_codes: dict[str, SportyBetBooking] = field(default_factory=dict)

    def all_option_codes(self) -> list[tuple[str, Accumulator]]:
        out: list[tuple[str, Accumulator]] = []
        for key in ("3odd", "5odd", "50odd"):
            for acc in self.accus.get(key, []):
                out.append((key, acc))
        return out


def build_daily_board(fixtures: list[Fixture], all_tips: list[Tip], settings) -> DailyBoard:
    specs = specs_from_settings(settings)
    day_label = datetime.now(timezone.utc).strftime("%a %d %b %Y")
    if fixtures:
        # Prefer local "today" label from caller; fallback first fixture date
        day_label = fixtures[0].date_str

    accus = {
        "3odd": build_accumulators(all_tips, specs["3odd"]),
        "5odd": build_accumulators(all_tips, specs["5odd"]),
        "50odd": build_accumulators(all_tips, specs["50odd"]),
    }
    tips_3 = list(accus["3odd"][0].legs) if accus["3odd"] else []
    tips_5 = list(accus["5odd"][0].legs) if accus["5odd"] else []
    tips_50 = list(accus["50odd"][0].legs) if accus["50odd"] else []

    return DailyBoard(
        fixtures=sorted(fixtures, key=lambda f: f.kickoff),
        day_label=day_label,
        accus=accus,
        specs=specs,
        tips_3=tips_3,
        tips_5=tips_5,
        tips_50=tips_50,
    )


def format_daily_odds_report(board: DailyBoard, settings) -> str:
    lines = [
        format_accumulator_report(
            board.accus,
            board.specs or specs_from_settings(settings),
            day_label=board.day_label,
            fixture_count=len(board.fixtures),
        )
    ]
    # Prefixed fixture preview
    head = [
        "📅 FIXTURE PREVIEW",
    ]
    if board.fixtures:
        first = board.fixtures[0]
        last = board.fixtures[-1]
        if first.date_str != board.day_label:
            head.append(
                f"ℹ️ No matches on {board.day_label} — slate "
                f"{first.kickoff.strftime('%d %b')}→{last.kickoff.strftime('%d %b')}"
            )
        for f in board.fixtures[:8]:
            head.append(f"  • [{f.league_code}] {f.label} | {f.kickoff_str}")
        if len(board.fixtures) > 8:
            head.append(f"  … +{len(board.fixtures) - 8} more (/fixtures)")
    else:
        head.append("  No fixtures in window.")
    head.append("─" * 36)
    return "\n".join(head + [""] + lines)


def format_band_singles(
    tips: list[Tip],
    title: str,
    target: float,
    min_conf: float,
    *,
    band_key: str = "",
    band_codes: dict[str, SportyBetBooking] | None = None,
    board: DailyBoard | None = None,
) -> str:
    """Band report — prefers full acca options when board is provided."""
    if board and band_key and board.specs.get(band_key):
        return format_band_accus(board.accus.get(band_key, []), board.specs[band_key])
    # Fallback minimal
    lines = [
        title,
        f"Target ≈ {target:.1f} | conf ≥ {min_conf:.0f}%",
        f"Picks: {len(tips)}",
    ]
    if not tips:
        lines.append("(no ticket — /safety)")
    for i, tip in enumerate(tips, start=1):
        p = tip.prediction
        f = tip.fixture
        lines.append(f"  {i}. [{f.league_code}] {f.label}")
        lines.append(f"     {p.market_label} @{p.display_odds:.2f} (conf {p.confidence:.0f}%)")
    return "\n".join(lines)


def format_fixtures_list(fixtures: list[Fixture], day_label: str) -> str:
    lines = [
        "📅 TODAY'S FIXTURES",
        f"Day: {day_label}",
        f"Count: {len(fixtures)}",
        "─" * 36,
    ]
    if not fixtures:
        lines.append("No fixtures loaded for today.")
        return "\n".join(lines)
    for i, f in enumerate(fixtures, start=1):
        lines.append(f"{i}. [{f.league_code}] {f.label}")
        lines.append(f"   Date: {f.kickoff_str}")
    return "\n".join(lines)


def format_sportybet_codes_report(board: DailyBoard) -> str:
    """SportyBet booking codes for every ticket option."""
    lines = [
        "🎫 SPORTYBET BOOKING CODES",
        f"Day: {board.day_label}",
        "Paste into SportyBet → Betslip → Booking Code → Load",
        "─" * 36,
    ]
    any_code = False
    labels = {"3odd": "≈3.0 (3 matches)", "5odd": "≈5.0 (3–5 matches)", "50odd": "≈50 (5–15 matches)"}
    for key in ("3odd", "5odd", "50odd"):
        lines.append("")
        lines.append(f"📌 {labels[key]}")
        group = board.accus.get(key, [])
        if not group:
            lines.append("  (no ticket)")
            continue
        for acc in group:
            lines.append(
                f"  ▸ {acc.label} | @{acc.combined_odds:.2f} | "
                f"conf avg {acc.avg_confidence:.0f}% / min {acc.min_confidence:.0f}%"
            )
            if acc.sportybet_code:
                any_code = True
                lines.append(f"    CODE: {acc.sportybet_code}")
                if acc.sportybet_url:
                    lines.append(f"    {acc.sportybet_url}")
            else:
                lines.append("    CODE: (not matched)")
    lines.append("")
    if not any_code:
        lines.append("No SportyBet codes yet. Send /safety to refresh.")
    else:
        lines.append("Codes expire when the earliest match starts.")
    lines.append("Not betting advice.")
    return "\n".join(lines)
