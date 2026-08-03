"""Daily fixture odds board — today's matches with ≈3 / ≈5 / ≈50 singles + dates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.models import Fixture, Tip
from src.selector import OddsBand, select_best_for_band
from src.sportingbet import sportingbet_code, sportingbet_lines, sportingbet_selection


@dataclass
class DailyBoard:
    fixtures: list[Fixture]
    tips_3: list[Tip]
    tips_5: list[Tip]
    tips_50: list[Tip]
    day_label: str


def band_defs_from_settings(settings) -> dict[str, OddsBand]:
    return {
        "3odd": OddsBand(
            key="3odd",
            title="🛡️ DAILY ≈3.0 ODDS",
            target_odds=settings.target_odds,
            tolerance=settings.odds_tolerance,
            min_confidence=settings.safety_min_confidence,
            max_tips=settings.max_daily_tips,
            prefer_safety_markets=True,
        ),
        "5odd": OddsBand(
            key="5odd",
            title="🎯 DAILY ≈5.0 ODDS",
            target_odds=settings.target_odds_5,
            tolerance=settings.odds_tolerance_5,
            min_confidence=settings.odd5_min_confidence,
            max_tips=settings.max_tips_5,
            prefer_safety_markets=False,
        ),
        "50odd": OddsBand(
            key="50odd",
            title="🚀 DAILY ≈50 ODDS",
            target_odds=settings.target_odds_50,
            tolerance=settings.odds_tolerance_50,
            min_confidence=settings.odd50_min_confidence,
            max_tips=settings.max_tips_50,
            prefer_safety_markets=False,
        ),
    }


def build_daily_board(fixtures: list[Fixture], all_tips: list[Tip], settings) -> DailyBoard:
    bands = band_defs_from_settings(settings)
    day_label = datetime.now(timezone.utc).strftime("%a %d %b %Y")
    if fixtures:
        day_label = fixtures[0].date_str
    return DailyBoard(
        fixtures=sorted(fixtures, key=lambda f: f.kickoff),
        tips_3=select_best_for_band(all_tips, bands["3odd"]),
        tips_5=select_best_for_band(all_tips, bands["5odd"]),
        tips_50=select_best_for_band(all_tips, bands["50odd"]),
        day_label=day_label,
    )


def _format_tip_block(tips: list[Tip], title: str, target: float, min_conf: float) -> list[str]:
    lines = [
        title,
        f"Target ≈ {target:.1f} | confidence ≥ {min_conf:.0f}% | picks {len(tips)}",
    ]
    if not tips:
        lines.append("  (no qualifying daily tip)")
        return lines
    for i, tip in enumerate(tips, start=1):
        p = tip.prediction
        f = tip.fixture
        sb_code, sb_market = sportingbet_selection(p.market)
        lines.append(f"  {i}. [{f.league_code}] {f.home_team} vs {f.away_team}")
        lines.append(f"     Date: {f.kickoff_str}")
        lines.append(
            f"     Pick: {p.market_label} [{sb_code}] @ {p.display_odds:.2f} | "
            f"Conf {p.confidence:.0f}%"
        )
        lines.append(f"     Sportingbet: {sb_market}")
        lines.append(f"     SB Code: {sportingbet_code(tip)}")
    return lines


def format_daily_odds_report(board: DailyBoard, settings) -> str:
    lines = [
        "⚽ DAILY FIXTURE ODDS",
        f"Day: {board.day_label}",
        f"Fixtures today: {len(board.fixtures)}",
        "Bands: ≈3.0 · ≈5.0 · ≈50 (singles from today's matches)",
        "─" * 36,
    ]

    lines.append("")
    lines.append("📅 TODAY'S FIXTURES")
    if not board.fixtures:
        lines.append("  No upcoming fixtures found for today.")
        lines.append("  Tip: check API token / leagues, or try again later.")
    else:
        preview = board.fixtures[:12]
        for f in preview:
            lines.append(f"  • [{f.league_code}] {f.label}")
            lines.append(f"    Date: {f.kickoff_str}")
        if len(board.fixtures) > 12:
            lines.append(f"  … +{len(board.fixtures) - 12} more (use /fixtures)")

    lines.append("")
    lines.extend(
        _format_tip_block(
            board.tips_3,
            "🛡️ DAILY ≈3.0 ODDS",
            settings.target_odds,
            settings.safety_min_confidence,
        )
    )
    lines.append("")
    lines.extend(
        _format_tip_block(
            board.tips_5,
            "🎯 DAILY ≈5.0 ODDS",
            settings.target_odds_5,
            settings.odd5_min_confidence,
        )
    )
    lines.append("")
    lines.extend(
        _format_tip_block(
            board.tips_50,
            "🚀 DAILY ≈50 ODDS",
            settings.target_odds_50,
            settings.odd50_min_confidence,
        )
    )
    lines.append("")
    lines.append("Not betting advice. Stake responsibly.")
    lines.append("SB Code = Sportingbet helper (search market by code).")
    lines.append("Telegram: /tips /fixtures /3odd /5odd /50odd /status")
    return "\n".join(lines)


def format_band_singles(tips: list[Tip], title: str, target: float, min_conf: float) -> str:
    lines = _format_tip_block(tips, title, target, min_conf)
    lines.append("")
    lines.append("Each tip includes Date + Sportingbet code for easy placement.")
    lines.append("Not betting advice.")
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
