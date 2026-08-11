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
    # Accumulator leg counts (careful multi-match tickets)
    # ≈3.0 → exactly 3 matches, multiple options
    acca3_min_legs: int = field(default_factory=lambda: _env_int("ACCA3_MIN_LEGS", 3))
    acca3_max_legs: int = field(default_factory=lambda: _env_int("ACCA3_MAX_LEGS", 3))
    acca3_options: int = field(default_factory=lambda: _env_int("ACCA3_OPTIONS", 3))
    # ≈5.0 → 3 to 5 matches, multiple options
    acca5_min_legs: int = field(default_factory=lambda: _env_int("ACCA5_MIN_LEGS", 3))
    acca5_max_legs: int = field(default_factory=lambda: _env_int("ACCA5_MAX_LEGS", 5))
    acca5_options: int = field(default_factory=lambda: _env_int("ACCA5_OPTIONS", 3))
    # ≈50 → 5 to 15 matches
    acca50_min_legs: int = field(default_factory=lambda: _env_int("ACCA50_MIN_LEGS", 5))
    acca50_max_legs: int = field(default_factory=lambda: _env_int("ACCA50_MAX_LEGS", 15))
    acca50_options: int = field(default_factory=lambda: _env_int("ACCA50_OPTIONS", 2))
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
    # Daily matches only (default true). Uses TIMEZONE calendar day.
    daily_only: bool = field(default_factory=lambda: _env_bool("DAILY_ONLY", True))
    # Africa/Lagos works well for WAT users; use UTC if preferred
    timezone_name: str = field(
        default_factory=lambda: os.getenv("TIMEZONE", "Africa/Lagos").strip() or "Africa/Lagos"
    )
    # Used only when DAILY_ONLY=false
    days_ahead: int = field(default_factory=lambda: _env_int("DAYS_AHEAD", 1))
    # Also include fixtures in the next N hours (helps late evening / early slate)
    daily_include_next_hours: int = field(
        default_factory=lambda: _env_int("DAILY_INCLUDE_NEXT_HOURS", 24)
    )
    # If today has 0 fixtures (off-season / midweek), load next upcoming within N days
    empty_day_fallback_days: int = field(
        default_factory=lambda: _env_int("EMPTY_DAY_FALLBACK_DAYS", 21)
    )
    status_interval_hours: int = field(default_factory=lambda: _env_int("STATUS_INTERVAL_HOURS", 6))
    telegram_poll_seconds: int = field(default_factory=lambda: _env_int("TELEGRAM_POLL_SECONDS", 5))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    telegram_bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))
    # SportyBet.com real booking / share codes (requires curl_cffi)
    sportybet_enabled: bool = field(default_factory=lambda: _env_bool("SPORTYBET_ENABLED", True))
    sportybet_country: str = field(
        default_factory=lambda: os.getenv("SPORTYBET_COUNTRY", "ng").strip().lower() or "ng"
    )
    football_data_base_url: str = "https://api.football-data.org/v4"
    odds_api_base_url: str = "https://api.the-odds-api.com/v4"

    def use_demo(self) -> bool:
        if self.demo_mode:
            return True
        return not bool(self.football_data_api_token)


settings = Settings()
