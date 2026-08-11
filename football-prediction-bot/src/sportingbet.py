"""Sportingbet-friendly market codes for easy bet placement."""

from __future__ import annotations

from src.models import Tip

# Short codes users commonly search on Sportingbet / similar books
SPORTINGBET_MARKET: dict[str, tuple[str, str]] = {
    # key -> (SB short code, SB market name)
    "home_win": ("1", "Full Time Result — Home"),
    "draw": ("X", "Full Time Result — Draw"),
    "away_win": ("2", "Full Time Result — Away"),
    "home_or_draw": ("1X", "Double Chance — 1X"),
    "away_or_draw": ("X2", "Double Chance — X2"),
    "btts_yes": ("GG", "Both Teams To Score — Yes"),
    "btts_no": ("NG", "Both Teams To Score — No"),
    "over_25": ("O2.5", "Total Goals — Over 2.5"),
    "under_25": ("U2.5", "Total Goals — Under 2.5"),
    "over_35": ("O3.5", "Total Goals — Over 3.5"),
    "under_35": ("U3.5", "Total Goals — Under 3.5"),
    "over_45": ("O4.5", "Total Goals — Over 4.5"),
    "home_win_nil": ("1WN", "Home Win to Nil"),
    "away_win_nil": ("2WN", "Away Win to Nil"),
}


def sportingbet_selection(market_key: str) -> tuple[str, str]:
    """Return (short_code, sportingbet_market_name)."""
    if market_key in SPORTINGBET_MARKET:
        return SPORTINGBET_MARKET[market_key]
    if market_key.startswith("cs_"):
        parts = market_key.split("_")
        if len(parts) == 3:
            score = f"{parts[1]}-{parts[2]}"
            return (f"CS{score}", f"Correct Score — {score}")
    return (market_key.upper()[:8], market_key)


def team_short(name: str) -> str:
    """Compact team name for codes."""
    cleaned = (
        name.replace(" FC", "")
        .replace(" CF", "")
        .replace(" AFC", "")
        .replace(" United", " Utd")
        .strip()
    )
    if len(cleaned) <= 14:
        return cleaned
    return cleaned[:14].rstrip()


def sportingbet_code(tip: Tip) -> str:
    """
    One-line Sportingbet-style booking helper code.

    Example:
    SB|03Aug|PL|Valencia vs Villarreal|O3.5|@2.86
    """
    f = tip.fixture
    p = tip.prediction
    code, _ = sportingbet_selection(p.market)
    date_part = f.kickoff.strftime("%d%b")
    home = team_short(f.home_team)
    away = team_short(f.away_team)
    return (
        f"SB|{date_part}|{f.league_code}|{home} vs {away}|"
        f"{code}|@{p.display_odds:.2f}"
    )


def sportingbet_lines(tip: Tip) -> list[str]:
    """Extra display lines for tip blocks."""
    code, market_name = sportingbet_selection(tip.prediction.market)
    return [
        f"     Sportingbet: {market_name} [{code}]",
        f"     SB Code: {sportingbet_code(tip)}",
    ]
