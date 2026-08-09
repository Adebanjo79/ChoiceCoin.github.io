"""Unit tests for indicators and scoring (no live network)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.analysis.engine import analyze_symbol, format_report
from src.analysis.momentum import analyze_momentum
from src.analysis.trend import analyze_trend, higher_tf_summary
from src.analysis.why_valid import build_why_valid
from src.indicators.technical import ema, rsi
from src.models import Direction, NO_TRADE_MSG, TradeLevels, Verdict, SignalReport
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


def test_why_valid_futuretradebot_checklist():
    df = _synthetic_trend(bull=True)
    lines = build_why_valid(df, Direction.LONG)
    assert len(lines) == 8
    joined = "\n".join(lines)
    assert "EMA stack" in joined
    assert "EMA200" in joined
    assert "RSI(14)=" in joined
    assert "MACD hist" in joined
    assert "20-SMA" in joined
    assert "OBV" in joined
    assert "consolidation" in joined.lower()
    assert "S/R window" in joined


def test_htf_summary_uses_neutral():
    df = _synthetic_trend(bull=True)
    frames = {"Min15": df, "Min60": df, "Hour4": df, "Day1": df}
    htf = higher_tf_summary(frames)
    assert "1H" in htf and "4H" in htf and "D" in htf
    assert "WAIT" not in htf


def test_format_report_matches_signal_card():
    levels = TradeLevels(
        entry=0.000002959,
        stop_loss=0.000002900,
        take_profit_1=0.000003077,
        take_profit_2=0.000003107,
        take_profit_3=0.000003166,
        risk_reward=2.5,
        position_size=1000,
        risk_amount=10,
        rr_tp1=2.0,
        rr_tp2=2.5,
        rr_tp3=3.5,
    )
    report = SignalReport(
        symbol="PEPE_USDT",
        direction=Direction.LONG,
        confidence=78,
        verdict=Verdict.BUY,
        message="TRADE SETUP VALID",
        why_valid=[
            "EMA stack bullish (9/20/50/100/200)",
            "Price above EMA200 (0.00000286904)",
            "RSI(14)=69.4 (none divergence)",
            "MACD hist 0 · bullish",
            "Volume 1.32x 20-SMA (>=1.3x OK)",
            "OBV rising",
            "Not in tight consolidation",
            "S/R window: Support 0.000002864 / Resistance 0.0000029616",
        ],
        higher_tf_trend="1H BUY · 4H BUY · D NEUTRAL",
        levels=levels,
        estimated_holding_time="2h-12h",
        invalidation=[
            "Close below structure SL 0.0000029",
            "HTF (4H/D) flip against position",
            "Volume dries up and price re-enters prior range",
        ],
        factor_scores={
            "Trend": 90,
            "Momentum": 83,
            "Volume": 100,
            "Price Action": 100,
            "Smart Money Concepts": 30,
            "Futures Metrics": 45,
            "Fundamental Analysis": 40,
        },
        factor_aligned={
            "Trend": True,
            "Momentum": True,
            "Volume": True,
            "Price Action": True,
            "Smart Money Concepts": False,
            "Futures Metrics": True,
            "Fundamental Analysis": False,
        },
        factor_weights={
            "Trend": 0.25,
            "Momentum": 0.20,
            "Volume": 0.15,
            "Price Action": 0.15,
            "Smart Money Concepts": 0.15,
            "Futures Metrics": 0.05,
            "Fundamental Analysis": 0.05,
        },
        price=0.000002959,
    )
    text = format_report(report)
    assert "🟢 BUY · LONG PEPE_USDT" in text
    assert "Why valid" in text
    assert "Factor scores" in text
    assert "• trend: 90% (w25%) ✓" in text
    assert "• smc: 30% (w15%)" in text
    assert "Stop Loss:" in text
    assert "Est. hold: 2h-12h" in text
    assert "Major risks" not in text
