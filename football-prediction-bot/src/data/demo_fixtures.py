"""Demo fixtures and form data so the bot works without API keys."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.models import Fixture, TeamForm


def _today_kickoffs(count: int) -> list[datetime]:
    """Spread `count` kickoffs across the rest of today (UTC)."""
    now = datetime.now(timezone.utc)
    today_end = now.replace(hour=23, minute=50, second=0, microsecond=0)
    if today_end <= now:
        # Very late UTC — still keep demos "today" a few minutes ahead
        return [now + timedelta(minutes=5 + i * 3) for i in range(count)]

    span_seconds = (today_end - now).total_seconds()
    step = max(900, span_seconds / max(count, 1))  # at least 15 minutes apart
    kicks: list[datetime] = []
    for i in range(count):
        kick = now + timedelta(seconds=step * (i + 1) * 0.85)
        if kick > today_end:
            kick = today_end - timedelta(minutes=2 * (count - i))
        if kick <= now:
            kick = now + timedelta(minutes=5 + i)
        kicks.append(kick)
    return kicks


def demo_fixtures() -> list[Fixture]:
    """Demo slate scheduled for today only (UTC), across major leagues."""
    samples = [
        ("PL", "Premier League", "Arsenal", "Chelsea"),
        ("PL", "Premier League", "Liverpool", "Newcastle"),
        ("PL", "Premier League", "Brighton", "Aston Villa"),
        ("PD", "La Liga", "Real Madrid", "Sevilla"),
        ("PD", "La Liga", "Girona", "Athletic Club"),
        ("PD", "La Liga", "Valencia", "Villarreal"),
        ("BL1", "Bundesliga", "Bayern Munich", "Dortmund"),
        ("BL1", "Bundesliga", "Freiburg", "Wolfsburg"),
        ("BL1", "Bundesliga", "Stuttgart", "Hoffenheim"),
        ("FL1", "Ligue 1", "PSG", "Marseille"),
        ("FL1", "Ligue 1", "Lyon", "Nice"),
        ("FL1", "Ligue 1", "Lille", "Monaco"),
        ("SA", "Serie A", "Inter", "Juventus"),
        ("SA", "Serie A", "Atalanta", "Napoli"),
        ("SA", "Serie A", "Roma", "Lazio"),
        ("DED", "Eredivisie", "Ajax", "PSV"),
        ("DED", "Eredivisie", "Feyenoord", "AZ Alkmaar"),
        ("PPL", "Primeira Liga", "Benfica", "Porto"),
        ("PPL", "Primeira Liga", "Sporting CP", "Braga"),
        ("ELC", "Championship", "Leeds", "Leicester"),
        ("CL", "Champions League", "Barcelona", "Bayern Munich"),
        ("CL", "Champions League", "Man City", "Real Madrid"),
    ]
    kicks = _today_kickoffs(len(samples))
    fixtures: list[Fixture] = []
    for i, ((code, name, home, away), kick) in enumerate(zip(samples, kicks), start=1):
        fixtures.append(
            Fixture(
                id=f"demo-{i}",
                league_code=code,
                league_name=name,
                kickoff=kick,
                home_team=home,
                away_team=away,
                home_team_id=f"h-{i}",
                away_team_id=f"a-{i}",
                status="SCHEDULED",
                matchday=i % 20 + 1,
            )
        )
    return fixtures


def demo_team_forms() -> dict[str, TeamForm]:
    """Keyed by team name for demo matching."""
    raw = {
        "Arsenal": (10, 7, 2, 1, 22, 8, 5, 13, 3, 5, 9, 5, list("WWWDW")),
        "Chelsea": (10, 4, 3, 3, 15, 14, 5, 9, 6, 5, 6, 8, list("WDLLW")),
        "Liverpool": (10, 8, 1, 1, 26, 10, 5, 15, 4, 5, 11, 6, list("WWWWW")),
        "Newcastle": (10, 5, 2, 3, 18, 15, 5, 11, 6, 5, 7, 9, list("WLWDW")),
        "Brighton": (10, 4, 4, 2, 16, 14, 5, 9, 6, 5, 7, 8, list("DWDWL")),
        "Aston Villa": (10, 6, 2, 2, 19, 12, 5, 11, 5, 5, 8, 7, list("WWDLW")),
        "Real Madrid": (10, 8, 1, 1, 24, 9, 5, 14, 3, 5, 10, 6, list("WWWDW")),
        "Sevilla": (10, 3, 3, 4, 12, 16, 5, 8, 7, 5, 4, 9, list("LDLWD")),
        "Girona": (10, 5, 2, 3, 17, 14, 5, 10, 6, 5, 7, 8, list("WLWDL")),
        "Athletic Club": (10, 6, 3, 1, 18, 10, 5, 11, 4, 5, 7, 6, list("WDWWW")),
        "Valencia": (10, 3, 4, 3, 13, 14, 5, 8, 6, 5, 5, 8, list("DDLWL")),
        "Villarreal": (10, 5, 2, 3, 18, 15, 5, 11, 6, 5, 7, 9, list("WWLDL")),
        "Bayern Munich": (10, 8, 1, 1, 28, 11, 5, 16, 4, 5, 12, 7, list("WWWWL")),
        "Dortmund": (10, 6, 2, 2, 22, 14, 5, 13, 5, 5, 9, 9, list("WLWDW")),
        "Freiburg": (10, 4, 3, 3, 14, 14, 5, 9, 6, 5, 5, 8, list("DWLDW")),
        "Wolfsburg": (10, 3, 3, 4, 13, 16, 5, 8, 7, 5, 5, 9, list("LLDWD")),
        "Stuttgart": (10, 6, 2, 2, 20, 13, 5, 12, 5, 5, 8, 8, list("WWDLW")),
        "Hoffenheim": (10, 3, 2, 5, 15, 20, 5, 9, 9, 5, 6, 11, list("LLWDL")),
        "PSG": (10, 8, 2, 0, 27, 8, 5, 16, 3, 5, 11, 5, list("WWWDW")),
        "Marseille": (10, 5, 2, 3, 17, 14, 5, 11, 5, 5, 6, 9, list("WLWDW")),
        "Lyon": (10, 5, 3, 2, 16, 12, 5, 10, 5, 5, 6, 7, list("WDWWL")),
        "Nice": (10, 4, 4, 2, 14, 12, 5, 8, 5, 5, 6, 7, list("DDWWL")),
        "Lille": (10, 6, 2, 2, 18, 11, 5, 11, 4, 5, 7, 7, list("WWDLW")),
        "Monaco": (10, 6, 1, 3, 20, 14, 5, 12, 5, 5, 8, 9, list("WLWWL")),
        "Inter": (10, 8, 1, 1, 23, 8, 5, 13, 3, 5, 10, 5, list("WWWDW")),
        "Juventus": (10, 6, 3, 1, 16, 9, 5, 10, 3, 5, 6, 6, list("WDWWW")),
        "Atalanta": (10, 7, 1, 2, 24, 13, 5, 14, 5, 5, 10, 8, list("WWLWW")),
        "Napoli": (10, 6, 2, 2, 19, 12, 5, 11, 4, 5, 8, 8, list("WWDLW")),
        "Roma": (10, 5, 3, 2, 17, 13, 5, 10, 5, 5, 7, 8, list("WDWLW")),
        "Lazio": (10, 5, 2, 3, 16, 14, 5, 10, 6, 5, 6, 8, list("WLWDL")),
        "Ajax": (10, 5, 2, 3, 18, 15, 5, 11, 6, 5, 7, 9, list("WLWDW")),
        "PSV": (10, 8, 1, 1, 26, 9, 5, 15, 3, 5, 11, 6, list("WWWWW")),
        "Feyenoord": (10, 7, 2, 1, 22, 10, 5, 13, 4, 5, 9, 6, list("WWWDW")),
        "AZ Alkmaar": (10, 5, 3, 2, 17, 13, 5, 10, 5, 5, 7, 8, list("WDWLW")),
        "Benfica": (10, 7, 2, 1, 23, 9, 5, 14, 3, 5, 9, 6, list("WWWDW")),
        "Porto": (10, 7, 1, 2, 21, 10, 5, 13, 3, 5, 8, 7, list("WWLWW")),
        "Sporting CP": (10, 8, 1, 1, 25, 8, 5, 15, 2, 5, 10, 6, list("WWWWW")),
        "Braga": (10, 5, 2, 3, 16, 13, 5, 10, 5, 5, 6, 8, list("WLWDW")),
        "Leeds": (10, 7, 2, 1, 21, 9, 5, 13, 3, 5, 8, 6, list("WWWDW")),
        "Leicester": (10, 6, 2, 2, 19, 11, 5, 12, 4, 5, 7, 7, list("WDWWL")),
        "Barcelona": (10, 7, 2, 1, 24, 10, 5, 14, 4, 5, 10, 6, list("WWWDW")),
        "Man City": (10, 7, 2, 1, 25, 11, 5, 15, 4, 5, 10, 7, list("WWWDW")),
    }
    forms: dict[str, TeamForm] = {}
    for name, vals in raw.items():
        (
            played,
            wins,
            draws,
            losses,
            gf,
            ga,
            home_played,
            home_gf,
            home_ga,
            away_played,
            away_gf,
            away_ga,
            recent,
        ) = vals
        forms[name] = TeamForm(
            team_id=name.lower().replace(" ", "-"),
            team_name=name,
            played=played,
            wins=wins,
            draws=draws,
            losses=losses,
            goals_for=gf,
            goals_against=ga,
            home_played=home_played,
            home_gf=home_gf,
            home_ga=home_ga,
            away_played=away_played,
            away_gf=away_gf,
            away_ga=away_ga,
            recent_results=recent,
        )
    return forms
