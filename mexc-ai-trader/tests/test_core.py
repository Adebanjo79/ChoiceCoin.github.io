"""Unit tests for indicators and scoring (no live network)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from config import Settings
from src.analysis.engine import analyze_symbol, format_report
from src.analysis.momentum import analyze_momentum
from src.analysis.spot_metrics import analyze_spot_metrics
from src.analysis.trend import analyze_trend
from src.indicators.technical import ema, rsi
from src.mexc_client import display_symbol, normalize_spot_symbol
from src.models import Direction, NO_TRADE_MSG, SignalReport, Verdict
from src.risk import build_trade_levels


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


def test_normalize_spot_symbol():
    assert normalize_spot_symbol("BTC_USDT") == "BTCUSDT"
    assert normalize_spot_symbol("btc/usdt") == "BTCUSDT"
    assert display_symbol("BTCUSDT") == "BTC/USDT"


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


def test_spot_metrics_liquidity():
    result = analyze_spot_metrics(
        {
            "lastPrice": "1.0",
            "quoteVolume": "1000000",
            "bidPrice": "0.999",
            "askPrice": "1.001",
            "priceChangePercent": "4.5",
        },
        trades=[],
    )
    assert result.name == "Spot Metrics"
    assert result.weight == 0.05


def test_risk_levels_spot_50_usdt_50pct_tp3():
    df = _synthetic_trend(bull=True)
    levels = build_trade_levels(
        df,
        Direction.LONG,
        account_balance=50,
        min_rr=2.5,
        preferred_rr=3.0,
        target_upside_pct=50.0,
    )
    assert levels is not None
    assert levels.risk_reward >= 2.5
    assert levels.stop_loss < levels.entry < levels.take_profit_1
    assert levels.risk_amount == pytest.approx(0.5, rel=1e-3)
    # Cap spot notional at account
    assert levels.position_notional <= 50.0 + 1e-6
    # TP3 should stretch toward ~50% when structure allows
    assert levels.take_profit_3 >= levels.take_profit_2
    assert levels.upside_pct_tp3 > 0


def test_engine_no_trade_on_thin_conflict():
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
        account_balance_usdt=50,
        target_upside_pct=50,
        quality_filters=False,
    )
    report = analyze_symbol(
        "TESTUSDT",
        frames,
        ticker={
            "lastPrice": "100",
            "quoteVolume": "1000",
            "bidPrice": "100",
            "askPrice": "100.1",
            "priceChangePercent": "0.1",
        },
        deals=[],
        settings=settings,
    )
    assert report.verdict in (Verdict.NO_TRADE, Verdict.WAIT)
    assert NO_TRADE_MSG in report.message or report.direction == Direction.NONE
    assert "SPOT" in format_report(report) or "Spot" in format_report(report) or "spot" in format_report(report).lower()


def _synthetic_descending_breakout(n: int = 80) -> pd.DataFrame:
    """Build a descending channel then a strong upside breakout candle."""
    rng = np.random.default_rng(3)
    # Falling channel
    highs = np.linspace(120, 90, n - 1) + rng.normal(0, 0.3, n - 1)
    lows = np.linspace(100, 80, n - 1) + rng.normal(0, 0.3, n - 1)
    closes = (highs + lows) / 2
    opens = closes + rng.normal(0, 0.2, n - 1)
    vols = rng.uniform(800, 1200, n - 1)
    # Breakout candle
    last_open = closes[-1]
    last_close = last_open * 1.12
    last_high = last_close * 1.02
    last_low = last_open * 0.99
    open_ = np.append(opens, last_open)
    high = np.append(highs, last_high)
    low = np.append(lows, last_low)
    close = np.append(closes, last_close)
    volume = np.append(vols, float(vols[-20:].mean()) * 2.5)
    return pd.DataFrame(
        {
            "time": np.arange(n),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def test_breakout_detector_finds_channel_break():
    from src.analysis.breakout import detect_channel_breakout

    df = _synthetic_descending_breakout()
    setup = detect_channel_breakout(df, lookback=80)
    assert setup.direction in (Direction.LONG, Direction.NONE)
    assert setup.score > 40
    assert setup.volume_spike >= 1.0


def test_breakout_mode_target_defaults():
    settings = Settings(
        telegram_bot_token="",
        telegram_chat_id="",
        setup_mode="breakout",
        target_upside_pct=50,
        tp3_pct=800,
        max_stop_pct=0.08,
    )
    assert settings.effective_target_upside_pct() == 800.0
    assert settings.effective_max_stop_pct() >= 0.12


def test_pre_breakout_near_resistance():
    from src.analysis.breakout import detect_pre_breakout

    rng = np.random.default_rng(2)
    n = 60
    # Coil under 100 resistance
    close = np.concatenate([np.linspace(90, 98.5, n - 1) + rng.normal(0, 0.2, n - 1), [98.8]])
    high = np.maximum(close + 0.4, np.concatenate([np.full(n - 1, 100.0), [99.2]]))
    # Keep prior highs at resistance 100
    high[:-1] = np.maximum(high[:-1], 100.0)
    low = close - 0.8
    open_ = close - 0.2
    vol = np.concatenate([rng.uniform(800, 1000, n - 1), [1600.0]])
    df = pd.DataFrame(
        {"time": np.arange(n), "open": open_, "high": high, "low": low, "close": close, "volume": vol}
    )
    setup = detect_pre_breakout(df, lookback=60, near_pct=3.0)
    assert setup.pattern == "pre-breakout"
    assert setup.score >= 50


def test_daily_strong_buy_promote_floors_confidence():
    from src.scanner import MarketScanner
    from src.models import TradeLevels

    settings = Settings(
        telegram_bot_token="",
        telegram_chat_id="",
        min_confidence=80,
        daily_signal_target=3,
        force_strong_buy=True,
    )
    scanner = MarketScanner(settings)
    report = SignalReport(
        symbol="TESTUSDT",
        direction=Direction.LONG,
        confidence=72.0,
        verdict=Verdict.WAIT,
        message=NO_TRADE_MSG,
        levels=TradeLevels(1, 0.9, 1.5, 3, 9, 2.5, 1, 0.5, 50, 800),
    )
    out = scanner._promote_to_strong_buy(report, 1)
    assert out.verdict == Verdict.STRONG_BUY
    assert out.confidence >= 80


def test_moonshot_levels_50_to_800():
    from src.risk import build_moonshot_levels

    df = _synthetic_trend(bull=True)
    levels = build_moonshot_levels(df, account_balance=50, tp1_pct_pct=50, tp2_pct_pct=200, tp3_pct_pct=800)
    assert levels is not None
    assert levels.take_profit_1 > levels.entry
    assert levels.upside_pct_tp3 == 800
    # ~50% and ~200% and ~800%
    assert abs((levels.take_profit_1 / levels.entry - 1) * 100 - 50) < 1
    assert abs((levels.take_profit_2 / levels.entry - 1) * 100 - 200) < 1
    assert abs((levels.take_profit_3 / levels.entry - 1) * 100 - 800) < 1

def test_resistance_breakout_detector():
    from src.analysis.breakout import detect_resistance_breakout

    rng = np.random.default_rng(1)
    n = 60
    # Flat range then breakout
    close = np.concatenate([np.full(n - 1, 100.0) + rng.normal(0, 0.3, n - 1), [112.0]])
    high = np.concatenate([np.full(n - 1, 101.5), [114.0]])
    low = np.concatenate([np.full(n - 1, 98.5), [100.5]])
    open_ = np.concatenate([np.full(n - 1, 100.0), [101.0]])
    vol = np.concatenate([rng.uniform(800, 1000, n - 1), [2500.0]])
    df = pd.DataFrame(
        {"time": np.arange(n), "open": open_, "high": high, "low": low, "close": close, "volume": vol}
    )
    setup = detect_resistance_breakout(df, lookback=60)
    assert setup.score >= 50
    assert setup.pattern == "horizontal resistance"