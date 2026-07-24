"""Runtime configuration for the MEXC Spot AI trading assistant."""

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


def _env_list(name: str) -> list[str]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return []
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))
    # Default 50 USDT — matches "50 USDT upward / ~50% gain" spot goal
    account_balance_usdt: float = field(default_factory=lambda: _env_float("ACCOUNT_BALANCE_USDT", 50.0))
    # 70% + QUALITY_FILTERS is the recommended anti-spam mode
    min_confidence: float = field(default_factory=lambda: _env_float("MIN_CONFIDENCE", 70.0))
    scan_interval_seconds: int = field(default_factory=lambda: _env_int("SCAN_INTERVAL_SECONDS", 600))
    max_workers: int = field(default_factory=lambda: _env_int("MAX_WORKERS", 3))
    symbol_whitelist: list[str] = field(default_factory=lambda: _env_list("SYMBOL_WHITELIST"))
    newsapi_key: str = field(default_factory=lambda: os.getenv("NEWSAPI_KEY", ""))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    # MEXC Spot REST
    mexc_base_url: str = field(
        default_factory=lambda: os.getenv("MEXC_BASE_URL", "https://api.mexc.com").rstrip("/")
    )
    request_gap_seconds: float = field(default_factory=lambda: _env_float("REQUEST_GAP_SECONDS", 0.22))
    fetch_deals: bool = field(
        default_factory=lambda: os.getenv("FETCH_DEALS", "false").strip().lower() in {"1", "true", "yes"}
    )
    fetch_depth: bool = field(
        default_factory=lambda: os.getenv("FETCH_DEPTH", "false").strip().lower() in {"1", "true", "yes"}
    )
    telegram_status: bool = field(
        default_factory=lambda: os.getenv("TELEGRAM_STATUS", "false").strip().lower() in {"1", "true", "yes"}
    )
    status_progress_every: int = field(default_factory=lambda: _env_int("STATUS_PROGRESS_EVERY", 50))
    scan_mode: str = field(default_factory=lambda: os.getenv("SCAN_MODE", "fast").strip().lower() or "fast")
    min_turnover_usdt: float = field(default_factory=lambda: _env_float("MIN_TURNOVER_USDT", 300000.0))
    scan_top_n: int = field(default_factory=lambda: _env_int("SCAN_TOP_N", 200))
    quality_filters: bool = field(
        default_factory=lambda: os.getenv("QUALITY_FILTERS", "true").strip().lower() in {"1", "true", "yes"}
    )
    max_btc_volatility_pct: float = field(
        default_factory=lambda: _env_float("BTC_MAX_VOLATILITY_PCT", 1.20)
    )
    require_volume_above_avg: bool = field(
        default_factory=lambda: os.getenv("REQUIRE_VOLUME_ABOVE_AVG", "true").strip().lower()
        in {"1", "true", "yes"}
    )
    min_aligned_factors: int = field(default_factory=lambda: _env_int("MIN_ALIGNED_FACTORS", 2))
    # Spot growth target: TP3 aims near this % price move (default 50% on a 50 USDT book)
    target_upside_pct: float = field(default_factory=lambda: _env_float("TARGET_UPSIDE_PCT", 50.0))
    max_stop_pct: float = field(default_factory=lambda: _env_float("MAX_STOP_PCT", 0.08))
    risk_pct: float = 0.01
    min_rr: float = 2.5
    preferred_rr: float = 3.0
    volume_spike_mult: float = 1.5
    adx_min: float = 25.0
    news_blackout_minutes: int = 60
    kline_limit: int = 220
    timeframes: tuple[str, ...] = ("Min15", "Min60", "Hour4", "Day1")

    def active_timeframes(self) -> tuple[str, ...]:
        if self.scan_mode == "full":
            return self.timeframes
        return ("Min15", "Hour4", "Day1")

    def telegram_ready(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


settings = Settings()
