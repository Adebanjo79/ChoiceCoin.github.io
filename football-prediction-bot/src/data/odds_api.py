"""Optional The Odds API client for bookmaker prices."""

from __future__ import annotations

import logging
from typing import Any

import requests

from src.leagues import LEAGUES

logger = logging.getLogger(__name__)


class OddsApiClient:
    def __init__(self, api_key: str, base_url: str = "https://api.the-odds-api.com/v4") -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def h2h_odds_for_league(self, league_code: str) -> dict[str, dict[str, float]]:
        """
        Return map: 'Home vs Away' -> {'home_win': x, 'draw': y, 'away_win': z}
        using average bookmaker prices when available.
        """
        league = LEAGUES.get(league_code.upper())
        if not league or not league.odds_api_key:
            return {}
        try:
            resp = self.session.get(
                f"{self.base_url}/sports/{league.odds_api_key}/odds",
                params={
                    "apiKey": self.api_key,
                    "regions": "uk,eu",
                    "markets": "h2h,totals",
                    "oddsFormat": "decimal",
                },
                timeout=30,
            )
            if resp.status_code != 200:
                logger.warning("Odds API %s: %s", league_code, resp.text[:200])
                return {}
            return self._aggregate(resp.json())
        except Exception as exc:  # noqa: BLE001
            logger.warning("Odds API failed for %s: %s", league_code, exc)
            return {}

    def _aggregate(self, events: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for event in events:
            home = event.get("home_team", "")
            away = event.get("away_team", "")
            key = f"{home} vs {away}".lower()
            buckets: dict[str, list[float]] = {
                "home_win": [],
                "draw": [],
                "away_win": [],
                "over_25": [],
                "under_25": [],
            }
            for book in event.get("bookmakers", []):
                for market in book.get("markets", []):
                    mkey = market.get("key")
                    outcomes = market.get("outcomes", [])
                    if mkey == "h2h":
                        for o in outcomes:
                            name = o.get("name")
                            price = float(o.get("price", 0) or 0)
                            if price <= 1:
                                continue
                            if name == home:
                                buckets["home_win"].append(price)
                            elif name == away:
                                buckets["away_win"].append(price)
                            elif name.lower() == "draw":
                                buckets["draw"].append(price)
                    elif mkey == "totals":
                        for o in outcomes:
                            point = o.get("point")
                            price = float(o.get("price", 0) or 0)
                            if point != 2.5 or price <= 1:
                                continue
                            if o.get("name") == "Over":
                                buckets["over_25"].append(price)
                            elif o.get("name") == "Under":
                                buckets["under_25"].append(price)
            averaged = {
                k: sum(v) / len(v) for k, v in buckets.items() if v
            }
            if averaged:
                out[key] = averaged
        return out
