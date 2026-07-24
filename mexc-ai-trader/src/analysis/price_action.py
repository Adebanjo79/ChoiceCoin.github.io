"""Price action: S/R breakouts, retests, candlestick patterns, chop filter."""

from __future__ import annotations

import pandas as pd

from src.indicators.technical import atr
from src.models import Direction, FactorResult


def _is_choppy(df: pd.DataFrame, lookback: int = 20) -> bool:
    window = df.iloc[-lookback:]
    atr_now = float(atr(df, 14).iloc[-1])
    range_pct = (window["high"].max() - window["low"].min()) / window["close"].iloc[-1]
    # Tight range relative to ATR => chop
    return range_pct < (atr_now / window["close"].iloc[-1]) * 3.5


def _support_resistance(df: pd.DataFrame, lookback: int = 50) -> tuple[float, float]:
    window = df.iloc[-lookback:-1]
    return float(window["high"].max()), float(window["low"].min())


def _candle_patterns(df: pd.DataFrame) -> tuple[Direction | None, str]:
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    i = -1
    body = abs(c.iloc[i] - o.iloc[i])
    full = h.iloc[i] - l.iloc[i] + 1e-12
    upper = h.iloc[i] - max(c.iloc[i], o.iloc[i])
    lower = min(c.iloc[i], o.iloc[i]) - l.iloc[i]
    prev_body = abs(c.iloc[i - 1] - o.iloc[i - 1])

    # Engulfing
    bull_eng = (
        c.iloc[i - 1] < o.iloc[i - 1]
        and c.iloc[i] > o.iloc[i]
        and c.iloc[i] >= o.iloc[i - 1]
        and o.iloc[i] <= c.iloc[i - 1]
        and body > prev_body
    )
    bear_eng = (
        c.iloc[i - 1] > o.iloc[i - 1]
        and c.iloc[i] < o.iloc[i]
        and c.iloc[i] <= o.iloc[i - 1]
        and o.iloc[i] >= c.iloc[i - 1]
        and body > prev_body
    )
    if bull_eng:
        return Direction.LONG, "Bullish engulfing"
    if bear_eng:
        return Direction.SHORT, "Bearish engulfing"

    # Pin bar
    if lower > body * 2 and upper < body * 0.5:
        return Direction.LONG, "Bullish pin bar"
    if upper > body * 2 and lower < body * 0.5:
        return Direction.SHORT, "Bearish pin bar"

    # Morning / Evening star (simplified 3-candle)
    if len(df) >= 3:
        c1_bear = c.iloc[i - 2] < o.iloc[i - 2]
        c3_bull = c.iloc[i] > o.iloc[i]
        small_mid = abs(c.iloc[i - 1] - o.iloc[i - 1]) < abs(c.iloc[i - 2] - o.iloc[i - 2]) * 0.5
        if c1_bear and small_mid and c3_bull and c.iloc[i] > ((o.iloc[i - 2] + c.iloc[i - 2]) / 2):
            return Direction.LONG, "Morning star"
        c1_bull = c.iloc[i - 2] > o.iloc[i - 2]
        c3_bear = c.iloc[i] < o.iloc[i]
        if c1_bull and small_mid and c3_bear and c.iloc[i] < ((o.iloc[i - 2] + c.iloc[i - 2]) / 2):
            return Direction.SHORT, "Evening star"

    # Inside bar breakout
    inside = h.iloc[i - 1] < h.iloc[i - 2] and l.iloc[i - 1] > l.iloc[i - 2]
    if inside and c.iloc[i] > h.iloc[i - 1]:
        return Direction.LONG, "Inside bar bullish breakout"
    if inside and c.iloc[i] < l.iloc[i - 1]:
        return Direction.SHORT, "Inside bar bearish breakout"

    if body / full < 0.15:
        return None, "Doji / indecision"
    return None, "No strong candlestick confirmation"


def analyze_price_action(df: pd.DataFrame) -> FactorResult:
    details: list[str] = []
    if df is None or len(df) < 40:
        return FactorResult("Price Action", 0, Direction.NONE, ["Insufficient data"], False, 0.15)

    if _is_choppy(df):
        details.append("Consolidation / choppy market detected — avoid entries")
        return FactorResult(
            name="Price Action",
            score=15.0,
            direction=Direction.NONE,
            details=details,
            aligned=False,
            weight=0.15,
        )

    resistance, support = _support_resistance(df)
    price = float(df["close"].iloc[-1])
    prev = float(df["close"].iloc[-2])
    details.append(f"Key resistance≈{resistance:.4f} | support≈{support:.4f}")

    bull = 0
    bear = 0

    breakout = prev <= resistance and price > resistance
    breakdown = prev >= support and price < support
    # Retest: recent touch of broken level
    retest_long = False
    retest_short = False
    recent = df.iloc[-6:]
    if (recent["low"] <= resistance * 1.002).any() and price > resistance:
        retest_long = True
    if (recent["high"] >= support * 0.998).any() and price < support:
        retest_short = True

    if breakout:
        bull += 2
        details.append("Breakout above significant resistance")
        if retest_long:
            bull += 1
            details.append("Retest of breakout level held")
    elif breakdown:
        bear += 2
        details.append("Breakdown below significant support")
        if retest_short:
            bear += 1
            details.append("Retest of breakdown level held")
    else:
        details.append("No fresh S/R breakout/breakdown")

    candle_dir, candle_msg = _candle_patterns(df)
    details.append(f"Candle: {candle_msg}")
    if candle_dir == Direction.LONG:
        bull += 1
    elif candle_dir == Direction.SHORT:
        bear += 1

    if bull > bear:
        direction = Direction.LONG
        score = min(100.0, bull / 4 * 100)
    elif bear > bull:
        direction = Direction.SHORT
        score = min(100.0, bear / 4 * 100)
    else:
        direction = Direction.NONE
        score = 30.0

    return FactorResult(
        name="Price Action",
        score=score,
        direction=direction,
        details=details,
        aligned=score >= 60 and direction != Direction.NONE,
        weight=0.15,
    )
