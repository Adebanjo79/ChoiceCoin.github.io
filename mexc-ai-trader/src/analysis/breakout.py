"""Cryptobull-style spot setups: descending channel / wedge → upside breakout."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.indicators.technical import atr, swing_points
from src.models import Direction, FactorResult


@dataclass
class BreakoutSetup:
    found: bool
    score: float
    direction: Direction
    details: list[str]
    pattern: str = ""
    breakout_level: float = 0.0
    impulse_pct: float = 0.0
    volume_spike: float = 0.0


def _linreg(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    if len(x) < 2:
        return 0.0, float(y[-1]) if len(y) else 0.0
    slope, intercept = np.polyfit(x.astype(float), y.astype(float), 1)
    return float(slope), float(intercept)


def detect_channel_breakout(df: pd.DataFrame, lookback: int = 60) -> BreakoutSetup:
    """
    Detect a descending channel / falling-wedge style compression, then upside breakout.

    This mirrors the kind of spot swing setup in the LAUSDT example:
    lower-highs + lower-lows compression → strong green breakout candle + volume.
    """
    details: list[str] = []
    if df is None or len(df) < max(40, lookback // 2):
        return BreakoutSetup(False, 0.0, Direction.NONE, ["Insufficient bars for channel breakout"])

    window = df.iloc[-lookback:].reset_index(drop=True)
    if len(window) < 30:
        return BreakoutSetup(False, 0.0, Direction.NONE, ["Insufficient bars for channel breakout"])

    hi_idx, _ = swing_points(window["high"], 2, 2)
    _, lo_idx = swing_points(window["low"], 2, 2)

    # Fallback: sampled rolling extremes when swings are sparse
    if len(hi_idx) < 3 or len(lo_idx) < 3:
        step = max(3, len(window) // 8)
        hi_idx = list(range(step, len(window) - 3, step))
        lo_idx = list(range(step, len(window) - 3, step))
        # pick local extremes in each bucket
        hi_pick, lo_pick = [], []
        for i in hi_idx:
            seg = window["high"].iloc[max(0, i - 2) : i + 3]
            hi_pick.append(int(seg.idxmax()))
            seg_l = window["low"].iloc[max(0, i - 2) : i + 3]
            lo_pick.append(int(seg_l.idxmin()))
        hi_idx = sorted(set(hi_pick))
        lo_idx = sorted(set(lo_pick))

    if len(hi_idx) < 3 or len(lo_idx) < 3:
        return BreakoutSetup(False, 20.0, Direction.NONE, ["Not enough swing points for channel"])

    # Use last up-to-5 swings for resistance/support trendlines
    res_i = np.array(hi_idx[-5:], dtype=float)
    res_y = window["high"].iloc[hi_idx[-5:]].to_numpy(dtype=float)
    sup_i = np.array(lo_idx[-5:], dtype=float)
    sup_y = window["low"].iloc[lo_idx[-5:]].to_numpy(dtype=float)

    res_slope, res_int = _linreg(res_i, res_y)
    sup_slope, sup_int = _linreg(sup_i, sup_y)

    descending = res_slope < 0 and sup_slope <= 0
    compressing = res_slope < sup_slope  # falling wedge-ish (resistance falling faster)
    channel_like = descending and (compressing or abs(res_slope - sup_slope) < abs(res_slope) * 0.85)

    x_now = float(len(window) - 1)
    resist_now = res_slope * x_now + res_int
    support_now = sup_slope * x_now + sup_int
    price = float(window["close"].iloc[-1])
    prev = float(window["close"].iloc[-2])
    open_ = float(window["open"].iloc[-1])
    high = float(window["high"].iloc[-1])
    low = float(window["low"].iloc[-1])

    details.append(
        f"Channel slopes res/sup: {res_slope:.5f}/{sup_slope:.5f} "
        f"({'descending' if descending else 'not descending'})"
    )
    details.append(f"Trendline resistance≈{resist_now:.6f} | support≈{support_now:.6f}")

    if not channel_like and not descending:
        return BreakoutSetup(False, 25.0, Direction.NONE, details + ["No descending channel/wedge structure"])

    pattern = "falling wedge" if compressing and descending else "descending channel"
    details.append(f"Structure: {pattern}")

    # Breakout: close clears resistance trendline and prior swing high area
    recent_high = float(window["high"].iloc[:-1].tail(20).max())
    broke_line = prev <= resist_now * 1.002 and price > resist_now * 1.001
    broke_range = price > recent_high * 0.998 and prev <= recent_high
    impulse_pct = ((price - open_) / open_ * 100.0) if open_ else 0.0
    candle_range_pct = ((high - low) / open_ * 100.0) if open_ else 0.0
    strong_impulse = impulse_pct >= 3.0 or candle_range_pct >= 5.0

    vol = window["volume"]
    vol_avg = float(vol.iloc[-21:-1].mean()) if len(vol) > 21 else float(vol.mean())
    vol_now = float(vol.iloc[-1])
    vol_spike = (vol_now / vol_avg) if vol_avg > 0 else 0.0
    details.append(f"Breakout volume x{vol_spike:.2f} vs 20-avg")
    details.append(f"Impulse candle: {impulse_pct:.1f}% body / {candle_range_pct:.1f}% range")

    bullish_break = (broke_line or broke_range) and price > open_
    if not bullish_break:
        # Early watch: compressed descending structure but not broken yet
        score = 45.0 if channel_like else 30.0
        return BreakoutSetup(
            False,
            score,
            Direction.NONE,
            details + ["Compression intact — waiting for confirmed upside breakout"],
            pattern=pattern,
            breakout_level=float(resist_now),
        )

    score = 55.0
    if broke_line:
        score += 15
        details.append("Upside break of descending resistance trendline")
    if broke_range:
        score += 10
        details.append("Break above recent swing/range high")
    if vol_spike >= 1.5:
        score += 12
        details.append("Volume expansion confirms breakout")
    elif vol_spike >= 1.2:
        score += 6
        details.append("Mild volume expansion")
    else:
        details.append("Weak volume on breakout — lower conviction")
        score -= 8
    if strong_impulse:
        score += 10
        details.append("Strong impulse candle (Cryptobull-style expansion)")
    if compressing:
        score += 5
        details.append("Falling-wedge compression preceded breakout")

    # Avoid buying a wick-only fake break
    close_pos = (price - low) / (high - low + 1e-12)
    if close_pos < 0.45:
        score -= 15
        details.append("Close weak in candle range — possible fake break")

    score = float(min(100.0, max(0.0, score)))
    # Lower bar so aggressive mode catches more live breakouts
    found = score >= 55 and vol_spike >= 1.05 and (broke_line or broke_range)
    direction = Direction.LONG if found or score >= 55 else Direction.NONE

    atr_val = float(atr(window, 14).iloc[-1])
    details.append(f"ATR(14)≈{atr_val:.6f} | breakout level≈{resist_now:.6f}")

    return BreakoutSetup(
        found=found,
        score=score,
        direction=direction,
        details=details,
        pattern=pattern,
        breakout_level=float(resist_now),
        impulse_pct=float(impulse_pct),
        volume_spike=float(vol_spike),
    )


def detect_resistance_breakout(df: pd.DataFrame, lookback: int = 60) -> BreakoutSetup:
    """
    ESP-style setup: horizontal resistance / range high break with volume + impulse.
    """
    details: list[str] = []
    if df is None or len(df) < 35:
        return BreakoutSetup(False, 0.0, Direction.NONE, ["Insufficient bars for resistance breakout"])

    window = df.iloc[-lookback:].reset_index(drop=True)
    prior = window.iloc[:-1]
    resistance = float(prior["high"].tail(25).max())
    support = float(prior["low"].tail(25).min())
    price = float(window["close"].iloc[-1])
    prev = float(window["close"].iloc[-2])
    open_ = float(window["open"].iloc[-1])
    high = float(window["high"].iloc[-1])
    low = float(window["low"].iloc[-1])

    # Compression: range not exploding for most of lookback
    mid = prior.tail(20)
    range_pct = (float(mid["high"].max()) - float(mid["low"].min())) / max(price, 1e-12) * 100
    compressed = range_pct <= 45.0  # alts can still be wide; keep permissive

    vol = window["volume"]
    vol_avg = float(vol.iloc[-21:-1].mean()) if len(vol) > 21 else float(vol.mean())
    vol_now = float(vol.iloc[-1])
    vol_spike = (vol_now / vol_avg) if vol_avg > 0 else 0.0
    impulse_pct = ((price - open_) / open_ * 100.0) if open_ else 0.0
    broke = prev <= resistance * 1.002 and price > resistance * 1.001 and price > open_

    details.append(f"Range resistance≈{resistance:.6f} | support≈{support:.6f}")
    details.append(f"Prior 20-bar range≈{range_pct:.1f}% ({'compressed' if compressed else 'wide'})")
    details.append(f"Breakout volume x{vol_spike:.2f} | impulse {impulse_pct:.1f}%")

    if not broke:
        score = 40.0 if compressed else 25.0
        return BreakoutSetup(
            False,
            score,
            Direction.NONE,
            details + ["Waiting for clean close above resistance"],
            pattern="horizontal resistance",
            breakout_level=resistance,
            impulse_pct=impulse_pct,
            volume_spike=vol_spike,
        )

    score = 58.0
    details.append("Close broke above range / horizontal resistance")
    if compressed:
        score += 8
        details.append("Breakout from consolidation range")
    if vol_spike >= 1.5:
        score += 14
        details.append("Strong volume confirms breakout")
    elif vol_spike >= 1.2:
        score += 8
    else:
        score -= 6
        details.append("Volume not expanded enough")
    if impulse_pct >= 3.0:
        score += 10
        details.append("Strong bullish impulse candle")
    close_pos = (price - low) / (high - low + 1e-12)
    if close_pos < 0.45:
        score -= 12
        details.append("Weak close in candle — possible fakeout")

    score = float(min(100.0, max(0.0, score)))
    found = score >= 55 and vol_spike >= 1.05
    return BreakoutSetup(
        found=found,
        score=score,
        direction=Direction.LONG if found or score >= 55 else Direction.NONE,
        details=details,
        pattern="horizontal resistance",
        breakout_level=resistance,
        impulse_pct=impulse_pct,
        volume_spike=vol_spike,
    )


def analyze_breakout_setup(frames: dict[str, pd.DataFrame]) -> FactorResult:
    """Score Daily/4H for channel/wedge OR horizontal resistance breakouts."""
    day = frames.get("Day1")
    h4 = frames.get("Hour4")
    primary = frames.get("Min15")

    candidates: list[BreakoutSetup] = []

    def _add(df: pd.DataFrame | None, label: str, lookback: int) -> None:
        if df is None or getattr(df, "empty", True):
            return
        for detector in (detect_channel_breakout, detect_resistance_breakout):
            setup = detector(df, lookback=min(lookback, len(df)))
            setup.details = [f"[{label}] {x}" for x in setup.details]
            candidates.append(setup)

    _add(day, "Daily", 90)
    _add(h4, "4H", 80)
    if not candidates:
        _add(primary, "15m", 60)

    if not candidates:
        return FactorResult(
            name="Breakout Setup",
            score=0.0,
            direction=Direction.NONE,
            details=["No timeframe available for breakout scan"],
            aligned=False,
            weight=0.20,
        )

    best = max(candidates, key=lambda c: (c.found, c.score))
    details = list(best.details)
    if best.found or best.score >= 55:
        details.insert(0, f"CRYPTOBULL-STYLE SETUP: {best.pattern} breakout")
    return FactorResult(
        name="Breakout Setup",
        score=best.score,
        direction=best.direction if best.score >= 50 else Direction.NONE,
        details=details,
        aligned=best.found or best.score >= 55,
        weight=0.20,
    )
