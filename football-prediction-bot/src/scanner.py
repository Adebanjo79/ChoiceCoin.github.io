"""Daily scan orchestrator across leagues."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import schedule

from config import Settings
from src.analysis.engine import analyze_fixture, resolve_form, tips_from_predictions
from src.data.demo_fixtures import demo_fixtures, demo_team_forms
from src.data.football_data import FootballDataClient
from src.data.odds_api import OddsApiClient
from src.models import Fixture, TeamForm, Tip
from src.selector import format_daily_report, select_daily_tips
from src.telegram_alerter import TelegramAlerter

logger = logging.getLogger(__name__)


class PredictionScanner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.telegram = TelegramAlerter(settings.telegram_bot_token, settings.telegram_chat_id)
        self.fd: FootballDataClient | None = None
        self.odds: OddsApiClient | None = None
        if settings.football_data_api_token and not settings.use_demo():
            self.fd = FootballDataClient(
                settings.football_data_api_token, settings.football_data_base_url
            )
        if settings.odds_api_key:
            self.odds = OddsApiClient(settings.odds_api_key, settings.odds_api_base_url)

    def load_fixtures(self) -> list[Fixture]:
        if self.settings.use_demo() or self.fd is None:
            logger.info("Using DEMO fixtures (set FOOTBALL_DATA_API_TOKEN for live data)")
            fixtures = demo_fixtures()
            codes = set(self.settings.leagues)
            return [f for f in fixtures if f.league_code in codes]

        return self.fd.upcoming_fixtures(self.settings.leagues, days_ahead=7)

    def load_forms(self, fixtures: list[Fixture]) -> tuple[dict[str, TeamForm], dict[str, TeamForm]]:
        by_id: dict[str, TeamForm] = {}
        by_name: dict[str, TeamForm] = {}

        if self.settings.use_demo() or self.fd is None:
            by_name = demo_team_forms()
            return by_id, by_name

        leagues = {f.league_code for f in fixtures}
        for code in leagues:
            forms = self.fd.team_form_from_matches(code)
            by_id.update(forms)
            for form in forms.values():
                by_name[form.team_name] = form
        return by_id, by_name

    def load_book_odds(self) -> dict[str, dict[str, float]]:
        """Flattened map: 'home vs away'.lower() -> market odds."""
        if not self.odds:
            return {}
        merged: dict[str, dict[str, float]] = {}
        for code in self.settings.leagues:
            merged.update(self.odds.h2h_odds_for_league(code))
        return merged

    def analyze_all(self) -> list[Tip]:
        fixtures = self.load_fixtures()
        by_id, by_name = self.load_forms(fixtures)
        book_map = self.load_book_odds()
        all_tips: list[Tip] = []

        # league average GF approximation from forms
        league_avgs: dict[str, float] = defaultdict(list)
        for f in fixtures:
            home, away = resolve_form(f, by_id, by_name)
            league_avgs[f.league_code].append(home.avg_gf)
            league_avgs[f.league_code].append(away.avg_gf)

        for fixture in fixtures:
            home, away = resolve_form(fixture, by_id, by_name)
            avg_list = league_avgs.get(fixture.league_code) or [1.35]
            league_avg = sum(avg_list) / len(avg_list)
            key = fixture.label.lower()
            # also try swapped naming styles
            book = book_map.get(key, {})
            preds = analyze_fixture(
                fixture,
                home,
                away,
                markets=self.settings.markets,
                book_odds=book,
                league_avg_gf=league_avg,
            )
            all_tips.extend(tips_from_predictions(fixture, preds))

        logger.info(
            "Analyzed %d fixtures → %d market predictions",
            len(fixtures),
            len(all_tips),
        )
        return all_tips

    def run_daily(self) -> list[Tip]:
        tips = self.analyze_all()
        selected = select_daily_tips(
            tips,
            min_confidence=self.settings.min_confidence,
            target_odds=self.settings.target_odds,
            odds_tolerance=self.settings.odds_tolerance,
            max_tips=self.settings.max_daily_tips,
        )
        report = format_daily_report(
            selected,
            min_confidence=self.settings.min_confidence,
            target_odds=self.settings.target_odds,
        )
        print(report)
        if selected:
            self.telegram.send(report)
        else:
            logger.info("No tips met filters today")
        return selected

    def run_forever(self) -> None:
        hour = max(0, min(23, self.settings.run_hour_utc))
        schedule.every().day.at(f"{hour:02d}:00").do(self.run_daily)
        logger.info("Scheduled daily run at %02d:00 UTC", hour)
        # Also run once immediately
        self.run_daily()
        while True:
            schedule.run_pending()
            time.sleep(30)

    def export_json(self) -> list[dict[str, Any]]:
        selected = select_daily_tips(
            self.analyze_all(),
            min_confidence=self.settings.min_confidence,
            target_odds=self.settings.target_odds,
            odds_tolerance=self.settings.odds_tolerance,
            max_tips=self.settings.max_daily_tips,
        )
        return [
            {
                **t.to_dict(),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            for t in selected
        ]
