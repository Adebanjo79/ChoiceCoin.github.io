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
DEFAULT_MARKETS = [
    "home_win",
    "draw",
    "away_win",
    "over_25",
    "under_25",
    "btts_yes",
    "btts_no",
    "away_or_draw",
    "home_or_draw",
    "over_35",
    "over_45",
    "home_win_nil",
    "away_win_nil",
]


@dataclass(frozen=True)
class Settings:
    football_data_api_token: str = field(
        default_factory=lambda: os.getenv("FOOTBALL_DATA_API_TOKEN", "").strip()
    )
    odds_api_key: str = field(default_factory=lambda: os.getenv("ODDS_API_KEY", "").strip())
    demo_mode: bool = field(default_factory=lambda: _env_bool("DEMO_MODE", False))
    min_confidence: float = field(default_factory=lambda: _env_float("MIN_CONFIDENCE", 70.0))
    safety_min_confidence: float = field(
        default_factory=lambda: _env_float("SAFETY_MIN_CONFIDENCE", 75.0)
    )
    # ~5.0 odds band
    odd5_min_confidence: float = field(
        default_factory=lambda: _env_float("ODD5_MIN_CONFIDENCE", 70.0)
    )
    # ~50.0 longshot band (correct scores) — lower absolute conf floor
    odd50_min_confidence: float = field(
        default_factory=lambda: _env_float("ODD50_MIN_CONFIDENCE", 60.0)
    )
    target_odds: float = field(default_factory=lambda: _env_float("TARGET_ODDS", 3.0))
    target_odds_5: float = field(default_factory=lambda: _env_float("TARGET_ODDS_5", 5.0))
    target_odds_50: float = field(default_factory=lambda: _env_float("TARGET_ODDS_50", 50.0))
    odds_tolerance: float = field(default_factory=lambda: _env_float("ODDS_TOLERANCE", 0.75))
    odds_tolerance_5: float = field(default_factory=lambda: _env_float("ODDS_TOLERANCE_5", 1.25))
    odds_tolerance_50: float = field(default_factory=lambda: _env_float("ODDS_TOLERANCE_50", 20.0))
    max_daily_tips: int = field(default_factory=lambda: _env_int("MAX_DAILY_TIPS", 3))
    max_tips_5: int = field(default_factory=lambda: _env_int("MAX_TIPS_5", 3))
    max_tips_50: int = field(default_factory=lambda: _env_int("MAX_TIPS_50", 3))
    min_daily_tips: int = field(default_factory=lambda: _env_int("MIN_DAILY_TIPS", 1))
    include_correct_scores: bool = field(
        default_factory=lambda: _env_bool("INCLUDE_CORRECT_SCORES", True)
    )
    # Accumulator leg counts
    # 3-odd safest: 1, 2 or 3 games combining to ~3.0
    acca3_min_legs: int = field(default_factory=lambda: _env_int("ACCA3_MIN_LEGS", 1))
    acca3_max_legs: int = field(default_factory=lambda: _env_int("ACCA3_MAX_LEGS", 3))
    # 5-odd: more than 3 games
    acca5_min_legs: int = field(default_factory=lambda: _env_int("ACCA5_MIN_LEGS", 4))
    acca5_max_legs: int = field(default_factory=lambda: _env_int("ACCA5_MAX_LEGS", 6))
    # 50-odd: even more games
    acca50_min_legs: int = field(default_factory=lambda: _env_int("ACCA50_MIN_LEGS", 7))
    acca50_max_legs: int = field(default_factory=lambda: _env_int("ACCA50_MAX_LEGS", 12))
    # Per-leg odds window for safer multi building
    acca_leg_odds_min: float = field(default_factory=lambda: _env_float("ACCA_LEG_ODDS_MIN", 1.20))
    acca_leg_odds_max: float = field(default_factory=lambda: _env_float("ACCA_LEG_ODDS_MAX", 2.35))
    leagues: list[str] = field(
        default_factory=lambda: [c.upper() for c in _env_list("LEAGUES", DEFAULT_LEAGUES)]
    )
    markets: list[str] = field(
        default_factory=lambda: [m.lower() for m in _env_list("MARKETS", DEFAULT_MARKETS)]
    )
    run_hour_utc: int = field(default_factory=lambda: _env_int("RUN_HOUR_UTC", 8))
    scan_interval_hours: int = field(default_factory=lambda: _env_int("SCAN_INTERVAL_HOURS", 24))
    # Daily matches only (today UTC). Set false + DAYS_AHEAD>1 for multi-day.
    daily_only: bool = field(default_factory=lambda: _env_bool("DAILY_ONLY", True))
    # Used only when DAILY_ONLY=false
    days_ahead: int = field(default_factory=lambda: _env_int("DAYS_AHEAD", 1))
    status_interval_hours: int = field(default_factory=lambda: _env_int("STATUS_INTERVAL_HOURS", 6))
    telegram_poll_seconds: int = field(default_factory=lambda: _env_int("TELEGRAM_POLL_SECONDS", 5))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    telegram_bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))
    football_data_base_url: str = "https://api.football-data.org/v4"
    odds_api_base_url: str = "https://api.the-odds-api.com/v4"

    def use_demo(self) -> bool:
        if self.demo_mode:
            return True
        return not bool(self.football_data_api_token)


settings = Settings()
