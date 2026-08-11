"""football-data.org API client (free token)."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from src.leagues import league_name
from src.models import Fixture, TeamForm

logger = logging.getLogger(__name__)


class FootballDataClient:
    def __init__(self, token: str, base_url: str = "https://api.football-data.org/v4") -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"X-Auth-Token": token})
        # Free tier = 10 calls/min — pace requests
        self._min_gap_seconds = 6.5
        self._last_call = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._min_gap_seconds:
            time.sleep(self._min_gap_seconds - elapsed)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        self._throttle()
        resp = self.session.get(url, params=params or {}, timeout=30)
        self._last_call = time.monotonic()
        if resp.status_code == 429:
            logger.warning("Rate limited — sleeping 60s then retrying once")
            time.sleep(60)
            self._throttle()
            resp = self.session.get(url, params=params or {}, timeout=30)
            self._last_call = time.monotonic()
            if resp.status_code == 429:
                raise RuntimeError("football-data.org rate limit hit — wait and retry")
        resp.raise_for_status()
        return resp.json()

    def upcoming_fixtures(
        self,
        league_codes: list[str],
        days_ahead: int = 1,
        *,
        daily_only: bool = True,
        timezone_name: str = "Africa/Lagos",
        include_next_hours: int = 24,
        empty_day_fallback_days: int = 21,
    ) -> list[Fixture]:
        """Load upcoming fixtures. Default: today's matches (local TZ) + next hours.

        If the daily window is empty (common in off-season), automatically widen
        to the next scheduled matches within empty_day_fallback_days.
        """
        from src.time_window import in_daily_window, local_day_bounds

        days_ahead = max(1, int(days_ahead))
        now = datetime.now(timezone.utc)
        fallback_days = max(0, int(empty_day_fallback_days))

        if daily_only:
            start_utc, end_utc, day_label = local_day_bounds(timezone_name)
            roll_end = now + timedelta(hours=max(0, include_next_hours))
            date_from = min(start_utc, now).date().isoformat()
            # Prefetch a wider API range so we can fall back without extra calls
            prefetch_end = now + timedelta(days=max(fallback_days, 1))
            date_to = max(end_utc, roll_end, prefetch_end).date().isoformat()
            window_label = f"daily/{day_label}"
        else:
            date_from = now.date().isoformat()
            date_to = (now + timedelta(days=days_ahead)).date().isoformat()
            window_label = f"next {days_ahead}d"
            fallback_days = 0

        all_upcoming: list[Fixture] = []
        for code in league_codes:
            try:
                data = self._get(
                    f"/competitions/{code}/matches",
                    {"status": "SCHEDULED", "dateFrom": date_from, "dateTo": date_to},
                )
            except Exception as exc:  # noqa: BLE001 — keep other leagues going
                logger.warning("Failed fixtures for %s: %s", code, exc)
                continue
            for match in data.get("matches", []):
                fixture = self._parse_fixture(match, code)
                if fixture.kickoff < now:
                    continue
                all_upcoming.append(fixture)

        if daily_only:
            fixtures = [
                f
                for f in all_upcoming
                if in_daily_window(
                    f.kickoff,
                    tz_name=timezone_name,
                    include_next_hours=include_next_hours,
                    now=now,
                )
            ]
            if not fixtures and fallback_days > 0:
                limit = now + timedelta(days=fallback_days)
                fixtures = [f for f in all_upcoming if f.kickoff <= limit]
                if fixtures:
                    first = min(fixtures, key=lambda f: f.kickoff)
                    last = max(fixtures, key=lambda f: f.kickoff)
                    window_label = (
                        f"fallback/next {fallback_days}d "
                        f"({first.kickoff.strftime('%d %b')}–{last.kickoff.strftime('%d %b')})"
                    )
                    logger.info(
                        "No fixtures today — using next %d days (%d matches, from %s)",
                        fallback_days,
                        len(fixtures),
                        first.kickoff_str,
                    )
            # Log per-league counts for the chosen set
            by_league: dict[str, int] = {}
            for f in fixtures:
                by_league[f.league_code] = by_league.get(f.league_code, 0) + 1
            for code in league_codes:
                logger.info(
                    "Loaded %s fixtures for %s (%s)",
                    by_league.get(code, 0),
                    code,
                    window_label,
                )
        else:
            fixtures = list(all_upcoming)
            by_league = {}
            for f in fixtures:
                by_league[f.league_code] = by_league.get(f.league_code, 0) + 1
            for code in league_codes:
                logger.info(
                    "Loaded %s fixtures for %s (%s)",
                    by_league.get(code, 0),
                    code,
                    window_label,
                )

        fixtures.sort(key=lambda f: f.kickoff)
        return fixtures

    def team_form_from_matches(self, league_code: str, limit: int = 10) -> dict[str, TeamForm]:
        """Build form tables from recently finished matches in a competition."""
        matches: list[dict[str, Any]] = []
        try:
            data = self._get(
                f"/competitions/{league_code}/matches",
                {"status": "FINISHED", "limit": 100},
            )
            matches = data.get("matches", [])
            # Pre-season: current campaign may be empty — fall back to prior season
            if not matches:
                prior = datetime.now(timezone.utc).year - 1
                data = self._get(
                    f"/competitions/{league_code}/matches",
                    {"status": "FINISHED", "season": prior, "limit": 100},
                )
                matches = data.get("matches", [])
                if matches:
                    logger.info("Using %s season form for %s", prior, league_code)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed finished matches for %s: %s", league_code, exc)
            return {}

        forms: dict[str, TeamForm] = {}

        def ensure(team: dict[str, Any]) -> TeamForm:
            tid = team["id"]
            key = str(tid)
            if key not in forms:
                forms[key] = TeamForm(team_id=tid, team_name=team["name"])
            return forms[key]

        matches = sorted(matches, key=lambda m: m.get("utcDate", ""))
        # Prefer the most recent slice for form
        for match in matches[-80:]:
            score = match.get("score", {}).get("fullTime") or {}
            hg, ag = score.get("home"), score.get("away")
            if hg is None or ag is None:
                continue
            home = ensure(match["homeTeam"])
            away = ensure(match["awayTeam"])
            self._apply_result(home, away, hg, ag)

        for form in forms.values():
            form.recent_results = form.recent_results[-limit:]
        return forms

    @staticmethod
    def _apply_result(home: TeamForm, away: TeamForm, hg: int, ag: int) -> None:
        home.played += 1
        away.played += 1
        home.goals_for += hg
        home.goals_against += ag
        away.goals_for += ag
        away.goals_against += hg
        home.home_played += 1
        home.home_gf += hg
        home.home_ga += ag
        away.away_played += 1
        away.away_gf += ag
        away.away_ga += hg

        if hg > ag:
            home.wins += 1
            away.losses += 1
            home.recent_results.append("W")
            away.recent_results.append("L")
        elif hg < ag:
            away.wins += 1
            home.losses += 1
            home.recent_results.append("L")
            away.recent_results.append("W")
        else:
            home.draws += 1
            away.draws += 1
            home.recent_results.append("D")
            away.recent_results.append("D")

    @staticmethod
    def _parse_fixture(match: dict[str, Any], league_code: str) -> Fixture:
        kickoff = datetime.fromisoformat(match["utcDate"].replace("Z", "+00:00"))
        return Fixture(
            id=str(match["id"]),
            league_code=league_code,
            league_name=league_name(league_code),
            kickoff=kickoff,
            home_team=match["homeTeam"]["name"],
            away_team=match["awayTeam"]["name"],
            home_team_id=match["homeTeam"]["id"],
            away_team_id=match["awayTeam"]["id"],
            status=match.get("status", "SCHEDULED"),
            matchday=match.get("matchday"),
            raw=match,
        )
