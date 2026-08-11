"""Daily scan orchestrator — today's fixtures with ≈3 / ≈5 / ≈50 odds + dates."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import schedule

from config import Settings
from src.analysis.engine import analyze_fixture, resolve_form, tips_from_predictions
from src.daily_board import (
    DailyBoard,
    build_daily_board,
    format_band_singles,
    format_daily_odds_report,
    format_fixtures_list,
    format_sportybet_codes_report,
)
from src.data.demo_fixtures import demo_fixtures, demo_team_forms
from src.data.football_data import FootballDataClient
from src.data.odds_api import OddsApiClient
from src.models import Fixture, TeamForm, Tip
from src.runtime_status import RuntimeStatus
from src.sportybet import (
    SportyBetClient,
    book_accumulator_options,
    sportybet_enabled,
)
from src.telegram_alerter import TelegramAlerter
from src.telegram_bot import TelegramCommandBot
from src.time_window import in_daily_window, local_day_bounds

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
        self._cached_board: DailyBoard | None = None
        self._cached_fixtures: list[Fixture] = []
        self._cached_band_reports: dict[str, str] = {}
        self._cached_report = "No tips yet. Send /safety to scan."
        self._cached_fixtures_report = "No fixtures yet. Send /safety to scan."
        self._cached_codes_report = "No SportyBet codes yet. Send /safety to scan."
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
            on_fixtures=self.cached_fixtures_report,
            on_codes=self.cached_codes_report,
        )

    def load_fixtures(self) -> list[Fixture]:
        days = max(1, int(self.settings.days_ahead))
        daily = bool(self.settings.daily_only)
        tz_name = self.settings.timezone_name
        hours = self.settings.daily_include_next_hours

        if self.settings.use_demo() or self.fd is None:
            logger.info(
                "Using DEMO fixtures (%s, tz=%s) — set FOOTBALL_DATA_API_TOKEN for live data",
                "daily" if daily else f"next {days}d",
                tz_name,
            )
            now = datetime.now(timezone.utc)
            fixtures = demo_fixtures()
            codes = set(self.settings.leagues)
            upcoming: list[Fixture] = []
            for f in fixtures:
                if f.league_code not in codes:
                    continue
                if f.kickoff < now:
                    continue
                upcoming.append(f)
            if daily:
                out = [
                    f
                    for f in upcoming
                    if in_daily_window(
                        f.kickoff,
                        tz_name=tz_name,
                        include_next_hours=hours,
                        now=now,
                    )
                ]
                if not out and self.settings.empty_day_fallback_days > 0:
                    limit = now + timedelta(days=self.settings.empty_day_fallback_days)
                    out = [f for f in upcoming if f.kickoff <= limit]
            else:
                out = [f for f in upcoming if f.kickoff <= now + timedelta(days=days)]
            return out

        return self.fd.upcoming_fixtures(
            self.settings.leagues,
            days_ahead=days,
            daily_only=daily,
            timezone_name=tz_name,
            include_next_hours=hours,
            empty_day_fallback_days=self.settings.empty_day_fallback_days,
        )

    def load_forms(self, fixtures: list[Fixture]) -> tuple[dict[str, TeamForm], dict[str, TeamForm]]:
        by_id: dict[str, TeamForm] = {}
        by_name: dict[str, TeamForm] = {}

        if self.settings.use_demo() or self.fd is None:
            by_name = demo_team_forms()
            return by_id, by_name

        leagues = {f.league_code for f in fixtures} or set(self.settings.leagues)
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

    def analyze_all(self) -> tuple[list[Tip], list[Fixture]]:
        fixtures = self.load_fixtures()
        self._cached_fixtures = fixtures
        by_id, by_name = self.load_forms(fixtures)
        book_map = self.load_book_odds()
        all_tips: list[Tip] = []

        league_avgs: dict[str, list[float]] = defaultdict(list)
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
            "Analyzed %d daily fixtures → %d market predictions",
            len(fixtures),
            len(all_tips),
        )
        return all_tips, fixtures

    def cached_tips_report(self) -> str:
        return self._cached_report

    def cached_fixtures_report(self) -> str:
        return self._cached_fixtures_report

    def cached_codes_report(self) -> str:
        return self._cached_codes_report

    def cached_band_report(self, band_key: str) -> str:
        if band_key in self._cached_band_reports:
            return self._cached_band_reports[band_key]
        return f"No {band_key} tips cached yet. Send /safety to refresh."

    def refresh_safety_report(self) -> str:
        self.run_daily(push_telegram=True)
        return self._cached_report

    def _attach_sportybet(self, board: DailyBoard) -> None:
        if not sportybet_enabled(self.settings):
            logger.info("SportyBet booking codes disabled")
            return
        client = SportyBetClient(country=self.settings.sportybet_country)
        board.band_codes = book_accumulator_options(
            board.accus,
            country=self.settings.sportybet_country,
            client=client,
        )
        coded = sum(
            1
            for group in board.accus.values()
            for acc in group
            if acc.sportybet_code
        )
        total = sum(len(v) for v in board.accus.values())
        logger.info(
            "SportyBet: %d/%d ticket options coded, first=%s",
            coded,
            total,
            {k: v.share_code for k, v in board.band_codes.items()},
        )

    def run_daily(self, *, push_telegram: bool = True) -> list[Tip]:
        self.status.mark_scan_start()
        try:
            all_tips, fixtures = self.analyze_all()
            board = build_daily_board(fixtures, all_tips, self.settings)
            _, _, day_label = local_day_bounds(self.settings.timezone_name)
            board.day_label = day_label
            self._attach_sportybet(board)
            report = format_daily_odds_report(board, self.settings)
            fixtures_report = format_fixtures_list(fixtures, day_label)
            codes_report = format_sportybet_codes_report(board)

            self._cached_board = board
            self._cached_report = report
            self._cached_fixtures_report = fixtures_report
            self._cached_codes_report = codes_report
            self._cached_tips = board.tips_3
            self._cached_band_reports = {
                "3odd": format_band_singles(
                    board.tips_3,
                    "🛡️ ≈3.0 ODDS — 3 MATCHES",
                    self.settings.target_odds,
                    self.settings.safety_min_confidence,
                    band_key="3odd",
                    band_codes=board.band_codes,
                    board=board,
                ),
                "5odd": format_band_singles(
                    board.tips_5,
                    "🎯 ≈5.0 ODDS — 3–5 MATCHES",
                    self.settings.target_odds_5,
                    self.settings.odd5_min_confidence,
                    band_key="5odd",
                    band_codes=board.band_codes,
                    board=board,
                ),
                "50odd": format_band_singles(
                    board.tips_50,
                    "🚀 ≈50 ODDS — 5–15 MATCHES",
                    self.settings.target_odds_50,
                    self.settings.odd50_min_confidence,
                    band_key="50odd",
                    band_codes=board.band_codes,
                    board=board,
                ),
                "fixtures": fixtures_report,
                "codes": codes_report,
            }

            total = sum(len(v) for v in board.accus.values())
            summary = (
                f"fixtures:{len(fixtures)} | "
                f"3odd:{len(board.accus.get('3odd', []))}opts "
                f"5odd:{len(board.accus.get('5odd', []))}opts "
                f"50odd:{len(board.accus.get('50odd', []))}opts"
            )
            self.status.mark_scan(
                fixtures=len(fixtures),
                predictions=len(all_tips),
                tips=total,
                summary=summary,
                ok=True,
            )
            print(report)
            if push_telegram and self.telegram.enabled:
                if self.telegram.send(report):
                    self.status.mark_telegram_push()
            elif total == 0:
                logger.info("No accumulator tickets met filters")
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

        logger.info("Scheduled daily fixture odds at %02d:00 UTC", hour)
        if self.telegram.enabled:
            self.telegram.send(
                "🟢 Careful Acca Bot online\n"
                f"Timezone: {self.settings.timezone_name}\n"
                "≈3.0 → 3 matches (options)\n"
                "≈5.0 → 3–5 matches (options)\n"
                "≈50 → 5–15 matches\n"
                "Each option has confidence + SportyBet code\n"
                f"Push time: {hour:02d}:00 UTC\n\n"
                "Try: /menu /3odd /5odd /50odd /codes /safety /tips"
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

    def export_json(self) -> dict[str, Any]:
        all_tips, fixtures = self.analyze_all()
        board = build_daily_board(fixtures, all_tips, self.settings)
        now = datetime.now(timezone.utc).isoformat()
        return {
            "generated_at": now,
            "day": board.day_label,
            "fixtures": [
                {
                    "league": f.league_code,
                    "match": f.label,
                    "date": f.date_str,
                    "kickoff": f.kickoff_str,
                }
                for f in board.fixtures
            ],
            "3odd": [a.to_dict() for a in board.accus.get("3odd", [])],
            "5odd": [a.to_dict() for a in board.accus.get("5odd", [])],
            "50odd": [a.to_dict() for a in board.accus.get("50odd", [])],
        }
