"""Helpers to resolve 'today' in a named timezone."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def resolve_tz(name: str):
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except Exception:  # noqa: BLE001
        return timezone.utc


def local_day_bounds(tz_name: str) -> tuple[datetime, datetime, str]:
    """Return (start_utc, end_utc, day_label) for 'today' in tz_name."""
    tz = resolve_tz(tz_name)
    now_local = datetime.now(tz)
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    label = now_local.strftime("%a %d %b %Y")
    return start_utc, end_utc, label


def in_daily_window(
    kickoff: datetime,
    *,
    tz_name: str,
    include_next_hours: int = 24,
    now: datetime | None = None,
) -> bool:
    """True if kickoff is later today (local) OR within the next include_next_hours."""
    now = now or datetime.now(timezone.utc)
    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=timezone.utc)
    if kickoff < now:
        return False

    start_utc, end_utc, _ = local_day_bounds(tz_name)
    if start_utc <= kickoff < end_utc:
        return True

    # Rolling window: next N hours from now (covers late-night / early morning)
    hours = max(0, int(include_next_hours))
    if hours and kickoff <= now + timedelta(hours=hours):
        return True
    return False
