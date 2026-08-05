"""Trend confirmation: EMAs, MTF, market structure."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.indicators.technical import ema, swing_points
from src.models import Direction, FactorResult


def _ema_alignment(close: pd.Series) -> tuple[Direction, list[str], float]:
    e9 = ema(close, 9).iloc[-1]
    e20 = ema(close, 20).iloc[-1]
    e50 = ema(close, 50).iloc[-1]
    e100 = ema(close, 100).iloc[-1]
    e200 = ema(close, 200).iloc[-1]
    price = close.iloc[-1]
    details: list[str] = []
    bull = e9 > e20 > e50 > e100 > e200 and price > e200
    bear = e9 < e20 < e50 < e100 < e200 and price < e200
    partial_bull = sum([e9 > e20, e20 > e50, e50 > e100, e100 > e200, price > e200])
    partial_bear = sum([e9 < e20, e20 < e50, e50 < e100, e100 < e200, price < e200])

    details.append(f"Price vs EMA200: {'above' if price > e200 else 'below'}")
    details.append(
        f"EMA stack 9/20/50/100/200: {e9:.4f}/{e20:.4f}/{e50:.4f}/{e100:.4f}/{e200:.4f}"
    )

    if bull:
        return Direction.LONG, details + ["Full bullish EMA alignment"], 100.0
    if bear:
        return Direction.SHORT, details + ["Full bearish EMA alignment"], 100.0
    if partial_bull >= 4:
        return Direction.LONG, details + [f"Partial bullish EMA ({partial_bull}/5)"], 70.0
    if partial_bear >= 4:
        return Direction.SHORT, details + [f"Partial bearish EMA ({partial_bear}/5)"], 70.0
    if partial_bull > partial_bear:
        return Direction.LONG, details + ["Mixed / incomplete bullish bias"], 40.0
    if partial_bear > partial_bull:
        return Direction.SHORT, details + ["Mixed / incomplete bearish bias"], 40.0
    return Direction.NONE, details + ["No EMA alignment"], 10.0


def _structure(df: pd.DataFrame) -> tuple[Direction, str, float]:
    highs_idx, lows_idx = swing_points(df["high"], 2, 2)
    _, lows_for_price = swing_points(df["low"], 2, 2)
    if len(highs_idx) < 2 or len(lows_for_price) < 2:
        return Direction.NONE, "Insufficient swing structure", 20.0

    hh = df["high"].iloc[highs_idx[-1]] > df["high"].iloc[highs_idx[-2]]
    hl = df["low"].iloc[lows_for_price[-1]] > df["low"].iloc[lows_for_price[-2]]
    lh = df["high"].iloc[highs_idx[-1]] < df["high"].iloc[highs_idx[-2]]
    ll = df["low"].iloc[lows_for_price[-1]] < df["low"].iloc[lows_for_price[-2]]

    if hh and hl:
        return Direction.LONG, "Market structure: HH + HL (uptrend)", 90.0
    if lh and ll:
        return Direction.SHORT, "Market structure: LH + LL (downtrend)", 90.0
    if hh or hl:
        return Direction.LONG, "Market structure: mixed bullish", 55.0
    if lh or ll:
        return Direction.SHORT, "Market structure: mixed bearish", 55.0
    return Direction.NONE, "Market structure: range / unclear", 25.0


def analyze_trend(frames: dict[str, pd.DataFrame]) -> FactorResult:
    """frames keys: Min15, Min60, Hour4, Day1."""
    details: list[str] = []
    votes: dict[Direction, float] = {Direction.LONG: 0, Direction.SHORT: 0, Direction.NONE: 0}
    tf_labels = {"Min15": "15m", "Min60": "1H", "Hour4": "4H", "Day1": "Daily"}
    weights = {"Min15": 0.15, "Min60": 0.25, "Hour4": 0.30, "Day1": 0.30}

    for tf, weight in weights.items():
        df = frames.get(tf)
        if df is None or len(df) < 210:
            details.append(f"{tf_labels.get(tf, tf)}: insufficient data")
            continue
        direction, ema_details, ema_score = _ema_alignment(df["close"])
        struct_dir, struct_msg, struct_score = _structure(df)
        combined = 0.6 * ema_score + 0.4 * struct_score
        final_dir = direction if direction != Direction.NONE else struct_dir
        if direction != Direction.NONE and struct_dir != Direction.NONE and direction != struct_dir:
            combined *= 0.5
            final_dir = Direction.NONE
            details.append(f"{tf_labels[tf]}: EMA vs structure conflict")
        else:
            details.append(f"{tf_labels[tf]}: {final_dir.value} (score {combined:.0f})")
        details.extend([f"  - {d}" for d in ema_details[-2:]])
        details.append(f"  - {struct_msg}")
        votes[final_dir] += weight * combined

    # Higher TF conflict check
    higher = []
    for tf in ("Hour4", "Day1"):
        df = frames.get(tf)
        if df is not None and len(df) >= 210:
            d, _, _ = _ema_alignment(df["close"])
            higher.append(d)
    conflict = (
        Direction.LONG in higher
        and Direction.SHORT in higher
        and Direction.NONE not in higher
        and len(set(higher)) > 1
    )

    best_dir = max(votes, key=votes.get)
    score = votes[best_dir] / max(sum(weights.values()), 1e-9)
    # normalize roughly to 0-100
    score = min(100.0, score)
    if conflict:
        score *= 0.4
        details.append("REJECT: conflicting higher-timeframe trends (4H vs Daily)")
        best_dir = Direction.NONE

    aligned = score >= 70 and best_dir != Direction.NONE
    htf = []
    for tf in ("Hour4", "Day1"):
        df = frames.get(tf)
        if df is not None and len(df) >= 210:
            d, _, _ = _ema_alignment(df["close"])
            htf.append(f"{tf_labels[tf]}={d.value}")
    details.insert(0, "HTF: " + (", ".join(htf) if htf else "n/a"))

    return FactorResult(
        name="Trend",
        score=score,
        direction=best_dir,
        details=details,
        aligned=aligned,
        weight=0.25,
    )


def higher_tf_summary(frames: dict[str, pd.DataFrame]) -> str:
    """Format like: 1H SELL · 4H SELL · D SELL"""
    parts = []
    for tf, label in (("Min60", "1H"), ("Hour4", "4H"), ("Day1", "D")):
        df = frames.get(tf)
        if df is None or len(df) < 210:
            # Fall back to Min15 bias label if 1H missing in ultra-fast mode
            if tf == "Min60":
                df15 = frames.get("Min15")
                if df15 is not None and len(df15) >= 210:
                    d, _, _ = _ema_alignment(df15["close"])
                    side = "BUY" if d == Direction.LONG else "SELL" if d == Direction.SHORT else "WAIT"
                    parts.append(f"{label} {side}")
                    continue
            parts.append(f"{label} n/a")
            continue
        d, _, _ = _ema_alignment(df["close"])
        side = "BUY" if d == Direction.LONG else "SELL" if d == Direction.SHORT else "WAIT"
        parts.append(f"{label} {side}")
    return " · ".join(parts)
