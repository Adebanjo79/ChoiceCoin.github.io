"""Runtime status shared by scanner and Telegram bot."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RuntimeStatus:
    started_at: datetime = field(default_factory=_utc_now)
    mode: str = "idle"  # idle | once | daemon | telegram
    last_scan_at: datetime | None = None
    last_scan_ok: bool = True
    last_error: str = ""
    last_fixture_count: int = 0
    last_prediction_count: int = 0
    last_tip_count: int = 0
    last_tips_summary: str = "No tips yet"
    last_telegram_push_at: datetime | None = None
    last_status_push_at: datetime | None = None
    scans_completed: int = 0
    demo_mode: bool = False
    min_confidence: float = 70.0
    safety_min_confidence: float = 75.0
    target_odds: float = 3.0
    max_daily_tips: int = 3
    leagues: list[str] = field(default_factory=list)

    def mark_scan_start(self) -> None:
        self.last_error = ""

    def mark_scan(
        self,
        *,
        fixtures: int,
        predictions: int,
        tips: int,
        summary: str,
        ok: bool = True,
        error: str = "",
    ) -> None:
        self.last_scan_at = _utc_now()
        self.last_scan_ok = ok
        self.last_error = error
        self.last_fixture_count = fixtures
        self.last_prediction_count = predictions
        self.last_tip_count = tips
        self.last_tips_summary = summary
        if ok:
            self.scans_completed += 1

    def mark_telegram_push(self) -> None:
        self.last_telegram_push_at = _utc_now()

    def mark_status_push(self) -> None:
        self.last_status_push_at = _utc_now()

    def uptime(self) -> str:
        delta = _utc_now() - self.started_at
        hours, rem = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(rem, 60)
        if hours:
            return f"{hours}h {minutes}m"
        if minutes:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"

    def format_status(self) -> str:
        last_scan = (
            self.last_scan_at.strftime("%Y-%m-%d %H:%M UTC") if self.last_scan_at else "never"
        )
        last_push = (
            self.last_telegram_push_at.strftime("%Y-%m-%d %H:%M UTC")
            if self.last_telegram_push_at
            else "never"
        )
        health = "OK" if self.last_scan_ok else "ERROR"
        lines = [
            "📡 BOT STATUS",
            f"Health: {health}",
            f"Mode: {self.mode}",
            f"Uptime: {self.uptime()}",
            f"Data: {'DEMO' if self.demo_mode else 'LIVE API'}",
            f"Safety filter: conf ≥ {self.safety_min_confidence:.0f}% | odds ≈ {self.target_odds:.2f}",
            f"Max daily safety tips: {self.max_daily_tips}",
            f"Leagues: {', '.join(self.leagues) or 'n/a'}",
            f"Scans completed: {self.scans_completed}",
            f"Last scan: {last_scan}",
            f"Fixtures analyzed: {self.last_fixture_count}",
            f"Market predictions: {self.last_prediction_count}",
            f"Tips selected: {self.last_tip_count}",
            f"Last Telegram tips push: {last_push}",
            "─" * 28,
            self.last_tips_summary,
        ]
        if self.last_error:
            lines.append(f"Last error: {self.last_error[:200]}")
        lines.append("Commands: /status /tips /safety /help")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "uptime": self.uptime(),
            "demo_mode": self.demo_mode,
            "last_scan_at": self.last_scan_at.isoformat() if self.last_scan_at else None,
            "last_tip_count": self.last_tip_count,
            "scans_completed": self.scans_completed,
            "health": "ok" if self.last_scan_ok else "error",
        }
