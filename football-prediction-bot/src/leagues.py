"""Supported competitions and market definitions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class League:
    code: str
    name: str
    country: str
    odds_api_key: str = ""  # sport key for The Odds API when available


LEAGUES: dict[str, League] = {
    "PL": League("PL", "Premier League", "England", "soccer_epl"),
    "PD": League("PD", "La Liga", "Spain", "soccer_spain_la_liga"),
    "BL1": League("BL1", "Bundesliga", "Germany", "soccer_germany_bundesliga"),
    "FL1": League("FL1", "Ligue 1", "France", "soccer_france_ligue_one"),
    "SA": League("SA", "Serie A", "Italy", "soccer_italy_serie_a"),
    "DED": League("DED", "Eredivisie", "Netherlands", "soccer_netherlands_eredivisie"),
    "PPL": League("PPL", "Primeira Liga", "Portugal", "soccer_portugal_primeira_liga"),
    "ELC": League("ELC", "Championship", "England", "soccer_efl_champ"),
    "CL": League("CL", "Champions League", "Europe", "soccer_uefa_champs_league"),
    "BSA": League("BSA", "Brasileirão", "Brazil", "soccer_brazil_campeonato"),
    "SPL": League("SPL", "Premiership", "Scotland", "soccer_spl"),
    "CLI": League("CLI", "Copa Libertadores", "South America", ""),
}


# Human-readable market labels used in tips
MARKET_LABELS: dict[str, str] = {
    "home_win": "Home Win (1)",
    "draw": "Draw (X)",
    "away_win": "Away Win (2)",
    "home_or_draw": "Double Chance 1X",
    "away_or_draw": "Double Chance X2",
    "btts_yes": "Both Teams To Score — Yes",
    "btts_no": "Both Teams To Score — No",
    "over_25": "Over 2.5 Goals",
    "under_25": "Under 2.5 Goals",
    "over_35": "Over 3.5 Goals",
    "under_35": "Under 3.5 Goals",
}


def league_name(code: str) -> str:
    league = LEAGUES.get(code.upper())
    return league.name if league else code
