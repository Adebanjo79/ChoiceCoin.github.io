"""Runtime configuration for the MEXC Spot AI trading assistant."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=True)


def _clean_env(value: str | None) -> str:
    """Strip spaces/quotes that break Telegram when pasted into .env."""
    if not value:
        return ""
    return value.strip().strip('"').strip("'").strip()


def _env_float(name: str, default: float) -> float:
    raw = _clean_env(os.getenv(name))
    return float(raw) if raw not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    raw = _clean_env(os.getenv(name))
    return int(raw) if raw not in (None, "") else default


def _env_list(name: str) -> list[str]:
    raw = _clean_env(os.getenv(name, ""))
    if not raw:
        return []
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str = field(
        default_factory=lambda: _clean_env(os.getenv("TELEGRAM_BOT_TOKEN", ""))
    )
    telegram_chat_id: str = field(
        default_factory=lambda: _clean_env(os.getenv("TELEGRAM_CHAT_ID", ""))
    )
    # Default 50 USDT — matches "50 USDT upward / ~50% gain" spot goal
    account_balance_usdt: float = field(default_factory=lambda: _env_float("ACCOUNT_BALANCE_USDT", 50.0))
    # Instant alerts only at this confidence (about-to-breakout / breakout)
    min_confidence: float = field(default_factory=lambda: _env_float("MIN_CONFIDENCE", 90.0))
    # Hard daily cap — never send more than this many STRONG BUY signals per UTC day
    daily_signal_target: int = field(default_factory=lambda: _env_int("DAILY_SIGNAL_TARGET", 5))
    force_strong_buy: bool = field(
        default_factory=lambda: os.getenv("FORCE_STRONG_BUY", "true").strip().lower()
        in {"1", "true", "yes"}
    )
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
    # Soft liquidity preference (USDT 24h quote volume). Top-N still fills to SCAN_TOP_N.
    min_turnover_usdt: float = field(default_factory=lambda: _env_float("MIN_TURNOVER_USDT", 100000.0))
    # Always aim to scan this many most-liquid spot pairs
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
    # standard = multi-factor scalp/swing | breakout = Cryptobull-style channel/wedge breakouts
    setup_mode: str = field(
        default_factory=lambda: os.getenv("SETUP_MODE", "breakout").strip().lower() or "breakout"
    )
    # In breakout mode, prefer coins already moving (24h abs % change)
    prefer_movers: bool = field(
        default_factory=lambda: os.getenv("PREFER_MOVERS", "true").strip().lower() in {"1", "true", "yes"}
    )
    min_mover_pct: float = field(default_factory=lambda: _env_float("MIN_MOVER_PCT", 5.0))
    # Aggressive breakout: fire alerts without institutional hard-blocks
    breakout_aggressive: bool = field(
        default_factory=lambda: os.getenv("BREAKOUT_AGGRESSIVE", "true").strip().lower()
        in {"1", "true", "yes"}
    )
    breakout_min_score: float = field(default_factory=lambda: _env_float("BREAKOUT_MIN_SCORE", 55.0))
    # Alert when price is within this % under resistance (early / about-to-break)
    pre_breakout_near_pct: float = field(default_factory=lambda: _env_float("PRE_BREAKOUT_NEAR_PCT", 3.0))
    pre_breakout_enabled: bool = field(
        default_factory=lambda: os.getenv("PRE_BREAKOUT", "true").strip().lower() in {"1", "true", "yes"}
    )
    tp1_pct: float = field(default_factory=lambda: _env_float("TP1_PCT", 50.0))
    tp2_pct: float = field(default_factory=lambda: _env_float("TP2_PCT", 200.0))
    tp3_pct: float = field(default_factory=lambda: _env_float("TP3_PCT", 800.0))
    risk_pct: float = 0.01
    min_rr: float = 2.5
    preferred_rr: float = 3.0
    volume_spike_mult: float = 1.5
    adx_min: float = 25.0
    news_blackout_minutes: int = 60
    kline_limit: int = 220
    timeframes: tuple[str, ...] = ("Min15", "Min60", "Hour4", "Day1")

    def active_timeframes(self) -> tuple[str, ...]:
        mode = self.scan_mode
        if self.setup_mode == "breakout":
            if mode == "full":
                return self.timeframes
            return ("Hour4", "Day1", "Min15")
        if mode == "full":
            return self.timeframes
        return ("Min15", "Hour4", "Day1")

    def effective_target_upside_pct(self) -> float:
        if self.setup_mode == "breakout":
            return self.tp3_pct
        return self.target_upside_pct

    def effective_max_stop_pct(self) -> float:
        if self.setup_mode == "breakout":
            return max(self.max_stop_pct, 0.12)
        return self.max_stop_pct

    def telegram_ready(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


settings = Settings()
