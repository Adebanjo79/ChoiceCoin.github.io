"""Runtime configuration for the football prediction bot."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw not in (None, "") else default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: list[str] | None = None) -> list[str]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return list(default or [])
    return [item.strip() for item in raw.split(",") if item.strip()]


DEFAULT_LEAGUES = ["PL", "PD", "BL1", "FL1", "SA", "DED", "PPL", "ELC", "CL"]
DEFAULT_MARKETS = ["draw", "away_win", "over_25", "btts_yes", "away_or_draw", "over_35"]


@dataclass(frozen=True)
class Settings:
    football_data_api_token: str = field(
        default_factory=lambda: os.getenv("FOOTBALL_DATA_API_TOKEN", "").strip()
    )
    odds_api_key: str = field(default_factory=lambda: os.getenv("ODDS_API_KEY", "").strip())
    demo_mode: bool = field(default_factory=lambda: _env_bool("DEMO_MODE", False))
    min_confidence: float = field(default_factory=lambda: _env_float("MIN_CONFIDENCE", 70.0))
    target_odds: float = field(default_factory=lambda: _env_float("TARGET_ODDS", 3.0))
    odds_tolerance: float = field(default_factory=lambda: _env_float("ODDS_TOLERANCE", 0.75))
    max_daily_tips: int = field(default_factory=lambda: _env_int("MAX_DAILY_TIPS", 5))
    min_daily_tips: int = field(default_factory=lambda: _env_int("MIN_DAILY_TIPS", 1))
    leagues: list[str] = field(
        default_factory=lambda: [c.upper() for c in _env_list("LEAGUES", DEFAULT_LEAGUES)]
    )
    markets: list[str] = field(
        default_factory=lambda: [m.lower() for m in _env_list("MARKETS", DEFAULT_MARKETS)]
    )
    run_hour_utc: int = field(default_factory=lambda: _env_int("RUN_HOUR_UTC", 8))
    scan_interval_hours: int = field(default_factory=lambda: _env_int("SCAN_INTERVAL_HOURS", 24))
    # Look ahead for fixtures (free-tier seasons often resume ~2–4 weeks out)
    days_ahead: int = field(default_factory=lambda: _env_int("DAYS_AHEAD", 30))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    telegram_bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))
    football_data_base_url: str = "https://api.football-data.org/v4"
    odds_api_base_url: str = "https://api.the-odds-api.com/v4"

    def use_demo(self) -> bool:
        """Demo when explicitly enabled or when no football-data token is set."""
        if self.demo_mode:
            return True
        return not bool(self.football_data_api_token)


settings = Settings()
