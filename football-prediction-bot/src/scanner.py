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
    OddsBand,
    format_daily_report,
    format_multi_band_report,
    select_best_for_band,
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
        self._cached_bands: dict[str, list[Tip]] = {"3odd": [], "5odd": [], "50odd": []}
        self._cached_band_reports: dict[str, str] = {}
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
            on_band=self.cached_band_report,
        )

    def band_defs(self) -> dict[str, OddsBand]:
        s = self.settings
        return {
            "3odd": OddsBand(
                key="3odd",
                title="🛡️ BEST 3-ODD",
                target_odds=s.target_odds,
                tolerance=s.odds_tolerance,
                min_confidence=s.safety_min_confidence,
                max_tips=s.max_daily_tips,
                prefer_safety_markets=True,
            ),
            "5odd": OddsBand(
                key="5odd",
                title="🎯 VALUE 5-ODD",
                target_odds=s.target_odds_5,
                tolerance=s.odds_tolerance_5,
                min_confidence=s.odd5_min_confidence,
                max_tips=s.max_tips_5,
            ),
            "50odd": OddsBand(
                key="50odd",
                title="🚀 LONGSHOT 50-ODD",
                target_odds=s.target_odds_50,
                tolerance=s.odds_tolerance_50,
                min_confidence=s.odd50_min_confidence,
                max_tips=s.max_tips_50,
            ),
        }

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
                include_correct_scores=self.settings.include_correct_scores,
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

    def select_all_bands(self, tips: list[Tip]) -> dict[str, list[Tip]]:
        bands = self.band_defs()
        return {key: select_best_for_band(tips, band) for key, band in bands.items()}

    def cached_tips_report(self) -> str:
        return self._cached_report

    def cached_band_report(self, band_key: str) -> str:
        if band_key in self._cached_band_reports:
            return self._cached_band_reports[band_key]
        return f"No {band_key} tips cached yet. Use /safety to refresh."

    def refresh_safety_report(self) -> str:
        self.run_daily(push_telegram=True)
        return self._cached_report

    def run_daily(self, *, push_telegram: bool = True) -> list[Tip]:
        self.status.mark_scan_start()
        try:
            all_tips, fixture_count = self.analyze_all()
            bands = self.select_all_bands(all_tips)
            meta = self.band_defs()
            report = format_multi_band_report(bands, meta)

            # Per-band cached reports for Telegram commands
            self._cached_bands = bands
            self._cached_band_reports = {
                key: format_daily_report(
                    tips,
                    min_confidence=meta[key].min_confidence,
                    target_odds=meta[key].target_odds,
                    title=meta[key].title,
                )
                for key, tips in bands.items()
            }
            self._cached_tips = bands.get("3odd", [])
            self._cached_report = report

            total_tips = sum(len(v) for v in bands.values())
            summary = (
                f"3odd:{len(bands['3odd'])} | 5odd:{len(bands['5odd'])} | "
                f"50odd:{len(bands['50odd'])} || "
                + short_tips_summary(bands["3odd"])
            )
            self.status.mark_scan(
                fixtures=fixture_count,
                predictions=len(all_tips),
                tips=total_tips,
                summary=summary,
                ok=True,
            )
            print(report)
            if push_telegram and self.telegram.enabled:
                if self.telegram.send(report):
                    self.status.mark_telegram_push()
            elif total_tips == 0:
                logger.info("No tips met filters today across bands")
            return bands.get("3odd", [])
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
        self.status.mode = "daemon"
        self.command_bot.setup()
        hour = max(0, min(23, self.settings.run_hour_utc))
        schedule.every().day.at(f"{hour:02d}:00").do(self.run_daily)

        status_hours = max(0, self.settings.status_interval_hours)
        if status_hours > 0:
            schedule.every(status_hours).hours.do(self.push_status)
            logger.info("Telegram status heartbeat every %sh", status_hours)

        logger.info("Scheduled daily multi-band tips at %02d:00 UTC", hour)
        if self.telegram.enabled:
            self.telegram.send(
                "🟢 Football Odds Bot online\n"
                f"Daily board: ≈3 / ≈5 / ≈50 odds @ {hour:02d}:00 UTC\n"
                f"3-odd safety conf ≥ {self.settings.safety_min_confidence:.0f}%\n"
                "Commands: /tips /3odd /5odd /50odd /status /safety"
            )
            self.status.mark_status_push()

        self.run_daily(push_telegram=True)

        poll = max(1, self.settings.telegram_poll_seconds)
        while True:
            schedule.run_pending()
            if self.telegram.bot_ready:
                self.command_bot.process_updates(timeout=poll)
            else:
                time.sleep(30)

    def export_json(self) -> dict[str, list[dict[str, Any]]]:
        all_tips, _ = self.analyze_all()
        bands = self.select_all_bands(all_tips)
        now = datetime.now(timezone.utc).isoformat()
        return {
            key: [{**t.to_dict(), "generated_at": now, "band": key} for t in tips]
            for key, tips in bands.items()
        }
