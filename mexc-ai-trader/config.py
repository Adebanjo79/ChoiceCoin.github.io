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
    telegram_bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))
    account_balance_usdt: float = field(default_factory=lambda: _env_float("ACCOUNT_BALANCE_USDT", 1000.0))
    min_confidence: float = field(default_factory=lambda: _env_float("MIN_CONFIDENCE", 80.0))
    scan_interval_seconds: int = field(default_factory=lambda: _env_int("SCAN_INTERVAL_SECONDS", 600))
    max_workers: int = field(default_factory=lambda: _env_int("MAX_WORKERS", 8))
    symbol_whitelist: list[str] = field(default_factory=lambda: _env_list("SYMBOL_WHITELIST"))
    newsapi_key: str = field(default_factory=lambda: os.getenv("NEWSAPI_KEY", ""))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    mexc_base_url: str = "https://contract.mexc.com"
    risk_pct: float = 0.01
    min_rr: float = 2.5
    preferred_rr: float = 3.0
    volume_spike_mult: float = 1.5
    adx_min: float = 25.0
    news_blackout_minutes: int = 60
    kline_limit: int = 250
    timeframes: tuple[str, ...] = ("Min15", "Min60", "Hour4", "Day1")

    def telegram_ready(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


settings = Settings()
