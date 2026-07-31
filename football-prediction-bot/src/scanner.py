"""Daily scan orchestrator — multi-game accumulators for ≈3 / ≈5 / ≈50 odds."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import schedule

from config import Settings
from src.accumulator import (
    AccaSpec,
    Accumulator,
    build_accumulators,
    format_accumulator_report,
    format_band_accus,
)
from src.analysis.engine import analyze_fixture, resolve_form, tips_from_predictions
from src.data.demo_fixtures import demo_fixtures, demo_team_forms
from src.data.football_data import FootballDataClient
from src.data.odds_api import OddsApiClient
from src.models import Fixture, TeamForm, Tip
from src.runtime_status import RuntimeStatus
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
        self._cached_accus: dict[str, list[Accumulator]] = {
            "3odd": [],
            "5odd": [],
            "50odd": [],
        }
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

    def acca_specs(self) -> dict[str, AccaSpec]:
        s = self.settings
        return {
            "3odd": AccaSpec(
                band_key="3odd",
                title="🛡️ SAFEST 3-ODD ACCA (1–3 games)",
                target_odds=s.target_odds,
                tolerance=s.odds_tolerance,
                min_confidence=s.safety_min_confidence,
                min_legs=s.acca3_min_legs,
                max_legs=s.acca3_max_legs,
                leg_odds_min=s.acca_leg_odds_min,
                leg_odds_max=min(s.acca_leg_odds_max, 2.50),
                prefer_safe_markets=True,
                max_accus=3,  # offer 1-game, 2-game, 3-game options
            ),
            "5odd": AccaSpec(
                band_key="5odd",
                title="🎯 5-ODD ACCA (4+ games)",
                target_odds=s.target_odds_5,
                tolerance=s.odds_tolerance_5,
                min_confidence=s.odd5_min_confidence,
                min_legs=s.acca5_min_legs,
                max_legs=s.acca5_max_legs,
                leg_odds_min=s.acca_leg_odds_min,
                leg_odds_max=s.acca_leg_odds_max,
                prefer_safe_markets=True,
                max_accus=2,
            ),
            "50odd": AccaSpec(
                band_key="50odd",
                title="🚀 50-ODD ACCA (7+ games)",
                target_odds=s.target_odds_50,
                tolerance=s.odds_tolerance_50,
                min_confidence=max(55.0, s.odd50_min_confidence - 5),
                min_legs=s.acca50_min_legs,
                max_legs=s.acca50_max_legs,
                # Longer per-leg prices so 7–12 folds can reach ≈50 combined
                leg_odds_min=max(1.35, s.acca_leg_odds_min),
                leg_odds_max=max(s.acca_leg_odds_max, 3.20),
                prefer_safe_markets=True,
                max_accus=2,
            ),
        }

    def load_fixtures(self) -> list[Fixture]:
        days = max(1, int(self.settings.days_ahead))
        if self.settings.use_demo() or self.fd is None:
            logger.info(
                "Using DEMO fixtures within next %s day(s) "
                "(set FOOTBALL_DATA_API_TOKEN for live data)",
                days,
            )
            from datetime import timedelta, timezone

            now = datetime.now(timezone.utc)
            cutoff = now + timedelta(days=days)
            fixtures = demo_fixtures()
            codes = set(self.settings.leagues)
            return [
                f
                for f in fixtures
                if f.league_code in codes and now <= f.kickoff <= cutoff
            ]

        return self.fd.upcoming_fixtures(self.settings.leagues, days_ahead=days)

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

    def select_all_accus(self, tips: list[Tip]) -> dict[str, list[Accumulator]]:
        specs = self.acca_specs()
        return {key: build_accumulators(tips, spec) for key, spec in specs.items()}

    # Back-compat alias used by older main paths
    def select_all_bands(self, tips: list[Tip]) -> dict[str, list[Tip]]:
        accus = self.select_all_accus(tips)
        # flatten first acca legs per band for any legacy caller
        return {k: (v[0].legs if v else []) for k, v in accus.items()}

    def cached_tips_report(self) -> str:
        return self._cached_report

    def cached_band_report(self, band_key: str) -> str:
        if band_key in self._cached_band_reports:
            return self._cached_band_reports[band_key]
        return f"No {band_key} accumulator cached yet. Use /safety to refresh."

    def refresh_safety_report(self) -> str:
        self.run_daily(push_telegram=True)
        return self._cached_report

    def run_daily(self, *, push_telegram: bool = True) -> list[Tip]:
        self.status.mark_scan_start()
        try:
            all_tips, fixture_count = self.analyze_all()
            accus = self.select_all_accus(all_tips)
            specs = self.acca_specs()
            report = format_accumulator_report(accus, specs)

            self._cached_accus = accus
            self._cached_band_reports = {
                key: format_band_accus(group, specs[key]) for key, group in accus.items()
            }
            self._cached_tips = accus["3odd"][0].legs if accus.get("3odd") else []
            self._cached_report = report

            total_legs = sum(a.leg_count for group in accus.values() for a in group)
            summary = (
                f"accas 3:{len(accus['3odd'])} 5:{len(accus['5odd'])} "
                f"50:{len(accus['50odd'])} | legs:{total_legs}"
            )
            self.status.mark_scan(
                fixtures=fixture_count,
                predictions=len(all_tips),
                tips=total_legs,
                summary=summary,
                ok=True,
            )
            print(report)
            if push_telegram and self.telegram.enabled:
                if self.telegram.send(report):
                    self.status.mark_telegram_push()
            elif total_legs == 0:
                logger.info("No accumulators met filters today")
            return self._cached_tips
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

        logger.info("Scheduled daily ACCA board at %02d:00 UTC", hour)
        if self.telegram.enabled:
            self.telegram.send(
                "🟢 Football Acca Bot online\n"
                "Daily tickets:\n"
                "• Safest ≈3.0 — 1 to 3 games\n"
                "• ≈5.0 — 4+ games\n"
                "• ≈50 — 7+ games\n"
                f"Push time: {hour:02d}:00 UTC\n"
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
        accus = self.select_all_accus(all_tips)
        now = datetime.now(timezone.utc).isoformat()
        return {
            key: [{**a.to_dict(), "generated_at": now} for a in group]
            for key, group in accus.items()
        }
