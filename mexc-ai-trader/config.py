"""Runtime configuration for the MEXC AI trading assistant."""

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
    telegram_bot_token: str = field(
        default_factory=lambda: (os.getenv("TELEGRAM_BOT_TOKEN", "") or "").strip().strip('"').strip("'")
    )
    telegram_chat_id: str = field(
        default_factory=lambda: (os.getenv("TELEGRAM_CHAT_ID", "") or "").strip().strip('"').strip("'")
    )
    account_balance_usdt: float = field(default_factory=lambda: _env_float("ACCOUNT_BALANCE_USDT", 1000.0))
    min_confidence: float = field(default_factory=lambda: _env_float("MIN_CONFIDENCE", 70.0))
    scan_interval_seconds: int = field(default_factory=lambda: _env_int("SCAN_INTERVAL_SECONDS", 600))
    max_workers: int = field(default_factory=lambda: _env_int("MAX_WORKERS", 3))
    symbol_whitelist: list[str] = field(default_factory=lambda: _env_list("SYMBOL_WHITELIST"))
    newsapi_key: str = field(default_factory=lambda: os.getenv("NEWSAPI_KEY", ""))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    mexc_base_url: str = "https://contract.mexc.com"
    # Seconds between each MEXC HTTP call (full-market scans need this)
    request_gap_seconds: float = field(default_factory=lambda: _env_float("REQUEST_GAP_SECONDS", 0.22))
    fetch_deals: bool = field(
        default_factory=lambda: os.getenv("FETCH_DEALS", "false").strip().lower() in {"1", "true", "yes"}
    )
    # Send Telegram status/heartbeat messages so you know the bot is alive
    telegram_status: bool = field(
        default_factory=lambda: os.getenv("TELEGRAM_STATUS", "false").strip().lower() in {"1", "true", "yes"}
    )
    # During long scans, send a progress ping every N finished coins
    status_progress_every: int = field(default_factory=lambda: _env_int("STATUS_PROGRESS_EVERY", 50))
    # fast = fewer timeframes + skip low-liquidity coins (much quicker)
    # full = all 4 timeframes on every pair
    scan_mode: str = field(default_factory=lambda: os.getenv("SCAN_MODE", "fast").strip().lower() or "fast")
    # Ignore quiet coins (USDT 24h turnover). 0 = keep all.
    min_turnover_usdt: float = field(default_factory=lambda: _env_float("MIN_TURNOVER_USDT", 300000.0))
    # After liquidity filter, analyze at most this many top movers (0 = all filtered)
    scan_top_n: int = field(default_factory=lambda: _env_int("SCAN_TOP_N", 200))
    # Quiet Telegram: false = only trade signals (no scan spam)
    # Quality filters for 70% confidence regime
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
    risk_pct: float = 0.01
    min_rr: float = 2.5
    preferred_rr: float = 2.5  # TP2 R:R (TP1=2.0, TP2=2.5, TP3=3.5)
    volume_spike_mult: float = 1.5
    adx_min: float = 25.0
    news_blackout_minutes: int = 60
    kline_limit: int = 220
    timeframes: tuple[str, ...] = ("Min15", "Min60", "Hour4", "Day1")

    def active_timeframes(self) -> tuple[str, ...]:
        if self.scan_mode == "full":
            return self.timeframes
        # Fast path: 15m entry + 1H/4H/D confirmation (FutureTradeBot-style HTF)
        return ("Min15", "Min60", "Hour4", "Day1")

    def telegram_ready(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


settings = Settings()
