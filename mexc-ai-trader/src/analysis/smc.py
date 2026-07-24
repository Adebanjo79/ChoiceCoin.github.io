"""Smart Money Concepts: BOS, CHoCH, order blocks, FVG, liquidity, premium/discount."""

from __future__ import annotations

import pandas as pd

from src.indicators.technical import ema, swing_points
from src.models import Direction, FactorResult


def _bos_choch(df: pd.DataFrame) -> tuple[Direction | None, list[str]]:
    details: list[str] = []
    hi_idx, _ = swing_points(df["high"], 2, 2)
    _, lo_idx = swing_points(df["low"], 2, 2)
    if len(hi_idx) < 2 or len(lo_idx) < 2:
        return None, ["Insufficient swings for BOS/CHoCH"]

    last_high = float(df["high"].iloc[hi_idx[-1]])
    last_low = float(df["low"].iloc[lo_idx[-1]])
    prev_high = float(df["high"].iloc[hi_idx[-2]])
    prev_low = float(df["low"].iloc[lo_idx[-2]])
    price = float(df["close"].iloc[-1])

    was_up = prev_high < last_high and prev_low < last_low
    was_down = prev_high > last_high and prev_low > last_low

    if price > last_high and was_up:
        details.append("BOS bullish: price broke prior swing high in uptrend")
        return Direction.LONG, details
    if price < last_low and was_down:
        details.append("BOS bearish: price broke prior swing low in downtrend")
        return Direction.SHORT, details
    if was_down and price > last_high:
        details.append("CHoCH bullish: structure shift from bearish to bullish")
        return Direction.LONG, details
    if was_up and price < last_low:
        details.append("CHoCH bearish: structure shift from bullish to bearish")
        return Direction.SHORT, details
    details.append("No fresh BOS/CHoCH")
    return None, details


def _order_blocks(df: pd.DataFrame) -> tuple[Direction | None, str]:
    for i in range(len(df) - 3, max(len(df) - 30, 2), -1):
        body = abs(df["close"].iloc[i] - df["open"].iloc[i])
        move = abs(df["close"].iloc[i + 1] - df["open"].iloc[i + 1])
        if move < body * 1.5:
            continue
        bullish_impulse = df["close"].iloc[i + 1] > df["open"].iloc[i + 1]
        bearish_candle = df["close"].iloc[i] < df["open"].iloc[i]
        bearish_impulse = df["close"].iloc[i + 1] < df["open"].iloc[i + 1]
        bullish_candle = df["close"].iloc[i] > df["open"].iloc[i]
        price = float(df["close"].iloc[-1])
        ob_low = float(min(df["open"].iloc[i], df["close"].iloc[i]))
        ob_high = float(max(df["open"].iloc[i], df["close"].iloc[i]))
        if bullish_impulse and bearish_candle and ob_low <= price <= ob_high * 1.01:
            return Direction.LONG, f"Price in bullish order block [{ob_low:.4f}-{ob_high:.4f}]"
        if bearish_impulse and bullish_candle and ob_low * 0.99 <= price <= ob_high:
            return Direction.SHORT, f"Price in bearish order block [{ob_low:.4f}-{ob_high:.4f}]"
    return None, "No active order block interaction"


def _fvg(df: pd.DataFrame) -> tuple[Direction | None, str]:
    for i in range(len(df) - 1, max(len(df) - 20, 2), -1):
        c0_high = float(df["high"].iloc[i - 2])
        c0_low = float(df["low"].iloc[i - 2])
        c2_high = float(df["high"].iloc[i])
        c2_low = float(df["low"].iloc[i])
        price = float(df["close"].iloc[-1])
        if c0_high < c2_low:
            if c0_high <= price <= c2_low:
                return Direction.LONG, f"Price filling bullish FVG [{c0_high:.4f}-{c2_low:.4f}]"
            if price > c2_low:
                return Direction.LONG, f"Bullish FVG left behind [{c0_high:.4f}-{c2_low:.4f}]"
        if c0_low > c2_high:
            if c2_high <= price <= c0_low:
                return Direction.SHORT, f"Price filling bearish FVG [{c2_high:.4f}-{c0_low:.4f}]"
            if price < c2_high:
                return Direction.SHORT, f"Bearish FVG left behind [{c2_high:.4f}-{c0_low:.4f}]"
    return None, "No notable FVG"


def _liquidity_sweep(df: pd.DataFrame) -> tuple[Direction | None, str]:
    hi_idx, _ = swing_points(df["high"], 2, 2)
    _, lo_idx = swing_points(df["low"], 2, 2)
    if not hi_idx or not lo_idx:
        return None, "No liquidity sweep"
    last_swing_high = float(df["high"].iloc[hi_idx[-1]])
    last_swing_low = float(df["low"].iloc[lo_idx[-1]])
    wick_high = float(df["high"].iloc[-1])
    wick_low = float(df["low"].iloc[-1])
    close = float(df["close"].iloc[-1])
    if wick_high > last_swing_high and close < last_swing_high:
        return Direction.SHORT, "Liquidity sweep above highs then close back inside"
    if wick_low < last_swing_low and close > last_swing_low:
        return Direction.LONG, "Liquidity sweep below lows then close back inside"
    return None, "No liquidity sweep"


def _premium_discount(df: pd.DataFrame) -> tuple[Direction | None, str]:
    window = df.iloc[-50:]
    high = float(window["high"].max())
    low = float(window["low"].min())
    mid = (high + low) / 2
    price = float(df["close"].iloc[-1])
    eq = float(ema(df["close"], 50).iloc[-1])
    if price < mid and price <= eq:
        return Direction.LONG, f"Discount zone (price {price:.4f} < mid {mid:.4f})"
    if price > mid and price >= eq:
        return Direction.SHORT, f"Premium zone (price {price:.4f} > mid {mid:.4f})"
    return None, f"Equilibrium zone near mid {mid:.4f}"


def analyze_smc(df: pd.DataFrame) -> FactorResult:
    details: list[str] = []
    if df is None or len(df) < 60:
        return FactorResult("Smart Money Concepts", 0, Direction.NONE, ["Insufficient data"], False, 0.15)

    checks: list[tuple[Direction | None, list[str]]] = []
    d, msgs = _bos_choch(df)
    checks.append((d, msgs))
    for fn in (_order_blocks, _fvg, _liquidity_sweep, _premium_discount):
        direction, msg = fn(df)
        checks.append((direction, [msg]))

    bull = 0
    bear = 0
    for direction, msgs in checks:
        details.extend(msgs)
        if direction == Direction.LONG:
            bull += 1
        elif direction == Direction.SHORT:
            bear += 1

    total = len(checks)
    if bull > bear:
        direction = Direction.LONG
        score = bull / total * 100
    elif bear > bull:
        direction = Direction.SHORT
        score = bear / total * 100
    else:
        direction = Direction.NONE
        score = 30.0

    return FactorResult(
        name="Smart Money Concepts",
        score=min(100.0, score),
        direction=direction,
        details=details,
        aligned=score >= 60 and direction != Direction.NONE,
        weight=0.15,
    )
