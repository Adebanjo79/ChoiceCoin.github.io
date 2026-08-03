"""Empty-day fixture fallback tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from src.data.football_data import FootballDataClient
from src.models import Fixture


def _match(fid: int, utc: datetime, home: str, away: str) -> dict:
    return {
        "id": fid,
        "utcDate": utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "SCHEDULED",
        "matchday": 1,
        "homeTeam": {"id": fid * 10, "name": home},
        "awayTeam": {"id": fid * 10 + 1, "name": away},
    }


def test_empty_today_falls_back_to_next_fixtures():
    now = datetime.now(timezone.utc)
    # Match well outside the "today + 24h" window, but within 21 days
    later = now + timedelta(days=10)

    client = FootballDataClient("fake-token")
    client._get = MagicMock(  # type: ignore[method-assign]
        return_value={"matches": [_match(1, later, "Arsenal", "Chelsea")]}
    )
    client._throttle = lambda: None  # type: ignore[method-assign]

    fixtures = client.upcoming_fixtures(
        ["PL"],
        daily_only=True,
        timezone_name="UTC",
        include_next_hours=24,
        empty_day_fallback_days=21,
    )
    assert len(fixtures) == 1
    assert fixtures[0].home_team == "Arsenal"


def test_empty_fallback_disabled_returns_nothing():
    now = datetime.now(timezone.utc)
    later = now + timedelta(days=10)
    client = FootballDataClient("fake-token")
    client._get = MagicMock(  # type: ignore[method-assign]
        return_value={"matches": [_match(2, later, "A", "B")]}
    )
    client._throttle = lambda: None  # type: ignore[method-assign]

    fixtures = client.upcoming_fixtures(
        ["PL"],
        daily_only=True,
        timezone_name="UTC",
        include_next_hours=24,
        empty_day_fallback_days=0,
    )
    assert fixtures == []
