"""Volume confirmation: spike, profile, OBV, CMF."""

from __future__ import annotations

import pandas as pd

from src.indicators.technical import cmf, obv, volume_profile_nodes
from src.models import Direction, FactorResult


def analyze_volume(df: pd.DataFrame, spike_mult: float = 1.5) -> FactorResult:
    details: list[str] = []
    if df is None or len(df) < 30:
        return FactorResult("Volume", 0, Direction.NONE, ["Insufficient data"], False, 0.15)

    vol = df["volume"]
    avg20 = float(vol.iloc[-21:-1].mean())
    cur = float(vol.iloc[-1])
    spike = avg20 > 0 and cur >= spike_mult * avg20
    details.append(
        f"Volume {'SPIKE' if spike else 'normal'}: {cur:.2f} vs 20-avg {avg20:.2f} "
        f"(need ≥{spike_mult}x)"
    )

    obv_s = obv(df)
    obv_slope = float(obv_s.iloc[-1] - obv_s.iloc[-6])
    cmf_s = cmf(df, 20)
    cmf_now = float(cmf_s.iloc[-1])
    profile = volume_profile_nodes(df.iloc[-80:])
    price = float(df["close"].iloc[-1])

    bull = 0
    bear = 0
    checks = 4

    if spike:
        # Direction inferred from candle
        if df["close"].iloc[-1] > df["open"].iloc[-1]:
            bull += 1
            details.append("Spike on bullish candle")
        elif df["close"].iloc[-1] < df["open"].iloc[-1]:
            bear += 1
            details.append("Spike on bearish candle")
        else:
            details.append("Spike on doji — weak")
    else:
        details.append(f"No {spike_mult}x volume confirmation")

    if obv_slope > 0:
        bull += 1
        details.append("OBV trending up")
    elif obv_slope < 0:
        bear += 1
        details.append("OBV trending down")
    else:
        details.append("OBV flat")

    if cmf_now > 0.05:
        bull += 1
        details.append(f"CMF positive ({cmf_now:.3f})")
    elif cmf_now < -0.05:
        bear += 1
        details.append(f"CMF negative ({cmf_now:.3f})")
    else:
        details.append(f"CMF neutral ({cmf_now:.3f})")

    poc = profile.get("poc")
    if poc == poc:  # not NaN
        details.append(f"Volume profile POC≈{poc:.4f} | HVN≈{profile['hvn']:.4f} | LVN≈{profile['lvn']:.4f}")
        if price > poc:
            bull += 1
            details.append("Price above POC (accepting higher value)")
        else:
            bear += 1
            details.append("Price below POC (accepting lower value)")

    if bull > bear:
        direction = Direction.LONG
        score = (bull / checks) * 100
    elif bear > bull:
        direction = Direction.SHORT
        score = (bear / checks) * 100
    else:
        direction = Direction.NONE
        score = 35.0

    if not spike:
        score *= 0.7

    return FactorResult(
        name="Volume",
        score=min(100.0, score),
        direction=direction,
        details=details,
        aligned=spike and direction != Direction.NONE and score >= 60,
        weight=0.15,
    )
