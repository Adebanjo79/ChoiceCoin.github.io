"""Unit tests for indicators and scoring (no live network)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.analysis.engine import analyze_symbol
from src.analysis.momentum import analyze_momentum
from src.analysis.trend import analyze_trend
from src.indicators.technical import ema, rsi
from src.models import Direction, NO_TRADE_MSG, Verdict
from src.risk import build_trade_levels
from config import Settings


def _synthetic_trend(n: int = 250, bull: bool = True) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    base = np.linspace(100, 140, n) if bull else np.linspace(140, 100, n)
    noise = rng.normal(0, 0.4, n)
    close = base + noise
    high = close + rng.uniform(0.2, 1.0, n)
    low = close - rng.uniform(0.2, 1.0, n)
    open_ = close + rng.normal(0, 0.2, n)
    vol = rng.uniform(1000, 5000, n)
    vol[-1] = vol[-20:-1].mean() * 2.0
    return pd.DataFrame(
        {
            "time": np.arange(n),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": vol,
        }
    )


def test_ema_rsi_basic():
    s = pd.Series(np.arange(1, 100, dtype=float))
    assert ema(s, 9).iloc[-1] > ema(s, 20).iloc[-1]
    r = rsi(s, 14)
    assert 50 < r.iloc[-1] <= 100


def test_trend_bullish_alignment():
    df = _synthetic_trend(bull=True)
    frames = {"Min15": df, "Min60": df, "Hour4": df, "Day1": df}
    result = analyze_trend(frames)
    assert result.direction in (Direction.LONG, Direction.NONE)
    assert 0 <= result.score <= 100


def test_momentum_returns_factor():
    df = _synthetic_trend(bull=True)
    result = analyze_momentum(df)
    assert result.name == "Momentum"
    assert result.weight == 0.20


def test_risk_levels_rr():
    df = _synthetic_trend(bull=True)
    levels = build_trade_levels(df, Direction.LONG, account_balance=1000, min_rr=2.5)
    assert levels is not None
    assert levels.risk_reward >= 2.5
    assert levels.stop_loss < levels.entry < levels.take_profit_1


def test_engine_no_trade_on_thin_conflict():
    # Flat/noisy data should usually produce NO TRADE / WAIT
    rng = np.random.default_rng(7)
    n = 250
    close = 100 + rng.normal(0, 0.3, n).cumsum() * 0.01
    df = pd.DataFrame(
        {
            "time": np.arange(n),
            "open": close,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "volume": rng.uniform(100, 200, n),
        }
    )
    frames = {"Min15": df, "Min60": df, "Hour4": df, "Day1": df}
    settings = Settings(
        telegram_bot_token="",
        telegram_chat_id="",
        min_confidence=85,
        account_balance_usdt=1000,
    )
    report = analyze_symbol(
        "TEST_USDT",
        frames,
        ticker={"fundingRate": 0, "holdVol": 1, "amount24": 1000, "bid1": 100, "ask1": 100.1},
        deals=[],
        settings=settings,
    )
    assert report.verdict in (Verdict.NO_TRADE, Verdict.WAIT)
    assert NO_TRADE_MSG in report.message or report.direction == Direction.NONE
