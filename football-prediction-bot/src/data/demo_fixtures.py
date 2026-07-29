"""Demo fixtures and form data so the bot works without API keys."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.models import Fixture, TeamForm


def _kickoff(hours_from_now: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours_from_now)


def demo_fixtures() -> list[Fixture]:
    """Realistic upcoming slate across major leagues for local demos."""
    samples = [
        ("PL", "Premier League", "Arsenal", "Chelsea", 8),
        ("PL", "Premier League", "Liverpool", "Newcastle", 12),
        ("PL", "Premier League", "Brighton", "Aston Villa", 30),
        ("PD", "La Liga", "Real Madrid", "Sevilla", 10),
        ("PD", "La Liga", "Girona", "Athletic Club", 26),
        ("PD", "La Liga", "Valencia", "Villarreal", 34),
        ("BL1", "Bundesliga", "Bayern Munich", "Dortmund", 14),
        ("BL1", "Bundesliga", "Freiburg", "Wolfsburg", 28),
        ("BL1", "Bundesliga", "Stuttgart", "Hoffenheim", 36),
        ("FL1", "Ligue 1", "PSG", "Marseille", 16),
        ("FL1", "Ligue 1", "Lyon", "Nice", 32),
        ("FL1", "Ligue 1", "Lille", "Monaco", 40),
        ("SA", "Serie A", "Inter", "Juventus", 18),
        ("SA", "Serie A", "Atalanta", "Napoli", 38),
        ("SA", "Serie A", "Roma", "Lazio", 44),
        ("DED", "Eredivisie", "Ajax", "PSV", 20),
        ("DED", "Eredivisie", "Feyenoord", "AZ Alkmaar", 42),
        ("PPL", "Primeira Liga", "Benfica", "Porto", 22),
        ("PPL", "Primeira Liga", "Sporting CP", "Braga", 46),
        ("ELC", "Championship", "Leeds", "Leicester", 24),
        ("CL", "Champions League", "Barcelona", "Bayern Munich", 50),
        ("CL", "Champions League", "Man City", "Real Madrid", 52),
    ]
    fixtures: list[Fixture] = []
    for i, (code, name, home, away, hours) in enumerate(samples, start=1):
        fixtures.append(
            Fixture(
                id=f"demo-{i}",
                league_code=code,
                league_name=name,
                kickoff=_kickoff(hours),
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
