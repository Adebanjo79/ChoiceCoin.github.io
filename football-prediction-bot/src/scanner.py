"""Daily scan orchestrator across leagues + Telegram delivery."""

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
from src.runtime_status import RuntimeStatus
from src.selector import (
    format_daily_report,
    select_daily_tips,
    select_safety_tips,
    short_tips_summary,
)
from src.telegram_alerter import TelegramAlerter
from src.telegram_bot import TelegramCommandBot

logger = logging.getLogger(__name__)


class PredictionScanner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.telegram = TelegramAlerter(settings.telegram_bot_token, settings.telegram_chat_id)
        self.status = RuntimeStatus(
            demo_mode=settings.use_demo(),
            min_confidence=settings.min_confidence,
            safety_min_confidence=settings.safety_min_confidence,
            target_odds=settings.target_odds,
            max_daily_tips=settings.max_daily_tips,
            leagues=list(settings.leagues),
        )
        self._cached_tips: list[Tip] = []
        self._cached_report = "No tips yet. Use /safety to scan."
        self.fd: FootballDataClient | None = None
        self.odds: OddsApiClient | None = None
        if settings.football_data_api_token and not settings.use_demo():
            self.fd = FootballDataClient(
                settings.football_data_api_token, settings.football_data_base_url
            )
        if settings.odds_api_key:
            self.odds = OddsApiClient(settings.odds_api_key, settings.odds_api_base_url)

        allowed = {settings.telegram_chat_id} if settings.telegram_chat_id else set()
        self.command_bot = TelegramCommandBot(
            self.telegram,
            self.status,
            allowed_chat_ids=allowed,
            on_safety_refresh=self.refresh_safety_report,
            on_tips=self.cached_tips_report,
        )

    def load_fixtures(self) -> list[Fixture]:
        if self.settings.use_demo() or self.fd is None:
            logger.info("Using DEMO fixtures (set FOOTBALL_DATA_API_TOKEN for live data)")
            fixtures = demo_fixtures()
            codes = set(self.settings.leagues)
            return [f for f in fixtures if f.league_code in codes]

        return self.fd.upcoming_fixtures(
            self.settings.leagues, days_ahead=self.settings.days_ahead
        )

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
        if not self.odds:
            return {}
        merged: dict[str, dict[str, float]] = {}
        for code in self.settings.leagues:
            merged.update(self.odds.h2h_odds_for_league(code))
        return merged

    def analyze_all(self) -> tuple[list[Tip], int]:
        """Return (all market tips, fixture count)."""
        fixtures = self.load_fixtures()
        by_id, by_name = self.load_forms(fixtures)
        book_map = self.load_book_odds()
        all_tips: list[Tip] = []

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
        return all_tips, len(fixtures)

    def select_safety(self, tips: list[Tip]) -> list[Tip]:
        return select_safety_tips(
            tips,
            min_confidence=self.settings.safety_min_confidence,
            target_odds=self.settings.target_odds,
            odds_tolerance=self.settings.odds_tolerance,
            max_tips=self.settings.max_daily_tips,
        )

    def cached_tips_report(self) -> str:
        return self._cached_report

    def refresh_safety_report(self) -> str:
        """Used by Telegram /safety — run scan and return report text."""
        self.run_daily(push_telegram=True)
        return self._cached_report

    def run_daily(self, *, push_telegram: bool = True) -> list[Tip]:
        self.status.mark_scan_start()
        try:
            all_tips, fixture_count = self.analyze_all()
            selected = self.select_safety(all_tips)
            report = format_daily_report(
                selected,
                min_confidence=self.settings.safety_min_confidence,
                target_odds=self.settings.target_odds,
                title="🛡️ SAFETY 3-ODD DAILY TIPS",
            )
            self._cached_tips = selected
            self._cached_report = report
            self.status.mark_scan(
                fixtures=fixture_count,
                predictions=len(all_tips),
                tips=len(selected),
                summary=short_tips_summary(selected),
                ok=True,
            )
            print(report)
            if push_telegram and self.telegram.enabled:
                # Always notify Telegram (tips or "no tips" status)
                if self.telegram.send(report):
                    self.status.mark_telegram_push()
            elif not selected:
                logger.info("No safety tips met filters today")
            return selected
        except Exception as exc:  # noqa: BLE001
            logger.exception("Daily scan failed: %s", exc)
            self.status.mark_scan(
                fixtures=0,
                predictions=0,
                tips=0,
                summary="Scan failed",
                ok=False,
                error=str(exc),
            )
            if push_telegram and self.telegram.enabled:
                self.telegram.send(f"⚠️ Scan failed:\n{exc}")
            return []

    def push_status(self) -> None:
        text = self.status.format_status()
        print(text)
        if self.telegram.enabled and self.telegram.send(text):
            self.status.mark_status_push()

    def run_forever(self) -> None:
        """Daily tips + status heartbeats + Telegram command polling."""
        self.status.mode = "daemon"
        self.command_bot.setup()
        hour = max(0, min(23, self.settings.run_hour_utc))
        schedule.every().day.at(f"{hour:02d}:00").do(self.run_daily)

        status_hours = max(0, self.settings.status_interval_hours)
        if status_hours > 0:
            schedule.every(status_hours).hours.do(self.push_status)
            logger.info("Telegram status heartbeat every %sh", status_hours)

        logger.info("Scheduled daily safety tips at %02d:00 UTC", hour)
        if self.telegram.enabled:
            self.telegram.send(
                "🟢 Football Safety Bot online\n"
                f"Daily tips ≈{self.settings.target_odds:.2f} odds @ "
                f"{hour:02d}:00 UTC\n"
                f"Safety conf ≥ {self.settings.safety_min_confidence:.0f}%\n"
                "Commands: /status /tips /safety /help"
            )
            self.status.mark_status_push()

        # Immediate first scan
        self.run_daily(push_telegram=True)

        poll = max(1, self.settings.telegram_poll_seconds)
        while True:
            schedule.run_pending()
            if self.telegram.bot_ready:
                self.command_bot.process_updates(timeout=poll)
            else:
                time.sleep(30)

    def export_json(self) -> list[dict[str, Any]]:
        all_tips, _ = self.analyze_all()
        selected = self.select_safety(all_tips)
        return [
            {
                **t.to_dict(),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            for t in selected
        ]
