"""Momentum confirmation: RSI, MACD, Stoch RSI, ADX."""

from __future__ import annotations

import pandas as pd

from src.indicators.technical import adx, macd, rsi, stochastic_rsi
from src.models import Direction, FactorResult


def _rsi_divergence(close: pd.Series, rsi_series: pd.Series, lookback: int = 30) -> str:
    if len(close) < lookback + 5:
        return "RSI divergence: insufficient data"
    c = close.iloc[-lookback:]
    r = rsi_series.iloc[-lookback:]
    price_ll = c.iloc[-1] < c.min() * 1.001 and c.iloc[-1] <= c.iloc[:-3].min()
    price_hh = c.iloc[-1] > c.max() * 0.999 and c.iloc[-1] >= c.iloc[:-3].max()
    rsi_hl = r.iloc[-1] > r.iloc[:-3].min()
    rsi_lh = r.iloc[-1] < r.iloc[:-3].max()
    if price_ll and rsi_hl:
        return "Bullish RSI divergence detected"
    if price_hh and rsi_lh:
        return "Bearish RSI divergence detected"
    return "No clear RSI divergence"


def analyze_momentum(df: pd.DataFrame, adx_min: float = 25.0) -> FactorResult:
    details: list[str] = []
    if df is None or len(df) < 50:
        return FactorResult("Momentum", 0, Direction.NONE, ["Insufficient data"], False, 0.20)

    close = df["close"]
    r = rsi(close, 14)
    m = macd(close)
    st = stochastic_rsi(close)
    adx_series = adx(df, 14)

    rsi_now = float(r.iloc[-1])
    rsi_prev = float(r.iloc[-2])
    macd_now, macd_prev = float(m["macd"].iloc[-1]), float(m["macd"].iloc[-2])
    sig_now, sig_prev = float(m["signal"].iloc[-1]), float(m["signal"].iloc[-2])
    hist_now, hist_prev = float(m["hist"].iloc[-1]), float(m["hist"].iloc[-2])
    k_now, d_now = float(st["k"].iloc[-1]), float(st["d"].iloc[-1])
    adx_now = float(adx_series.iloc[-1])

    bull_pts = 0
    bear_pts = 0
    total = 5

    # RSI trend
    if rsi_now > rsi_prev and rsi_now > 50:
        bull_pts += 1
        details.append(f"RSI(14) rising above 50 ({rsi_now:.1f})")
    elif rsi_now < rsi_prev and rsi_now < 50:
        bear_pts += 1
        details.append(f"RSI(14) falling below 50 ({rsi_now:.1f})")
    else:
        details.append(f"RSI(14) neutral ({rsi_now:.1f})")

    div = _rsi_divergence(close, r)
    details.append(div)
    if "Bullish" in div:
        bull_pts += 0.5
    elif "Bearish" in div:
        bear_pts += 0.5

    # MACD crossover + histogram
    bull_cross = macd_prev <= sig_prev and macd_now > sig_now
    bear_cross = macd_prev >= sig_prev and macd_now < sig_now
    if bull_cross or (hist_now > 0 and hist_now > hist_prev):
        bull_pts += 1
        details.append("MACD bullish (cross and/or rising hist)")
    elif bear_cross or (hist_now < 0 and hist_now < hist_prev):
        bear_pts += 1
        details.append("MACD bearish (cross and/or falling hist)")
    else:
        details.append("MACD inconclusive")

    # Stoch RSI
    if k_now > d_now and k_now < 80:
        bull_pts += 1
        details.append(f"Stoch RSI bullish ({k_now:.1f}/{d_now:.1f})")
    elif k_now < d_now and k_now > 20:
        bear_pts += 1
        details.append(f"Stoch RSI bearish ({k_now:.1f}/{d_now:.1f})")
    else:
        details.append(f"Stoch RSI extreme/neutral ({k_now:.1f}/{d_now:.1f})")

    # ADX
    if adx_now >= adx_min:
        details.append(f"ADX(14)={adx_now:.1f} (>= {adx_min}) strong trend")
        if bull_pts >= bear_pts:
            bull_pts += 1
        else:
            bear_pts += 1
    else:
        details.append(f"ADX(14)={adx_now:.1f} (< {adx_min}) weak/choppy — penalty")
        bull_pts *= 0.6
        bear_pts *= 0.6

    if bull_pts > bear_pts:
        direction = Direction.LONG
        score = min(100.0, (bull_pts / total) * 100)
    elif bear_pts > bull_pts:
        direction = Direction.SHORT
        score = min(100.0, (bear_pts / total) * 100)
    else:
        direction = Direction.NONE
        score = 30.0

    return FactorResult(
        name="Momentum",
        score=score,
        direction=direction,
        details=details,
        aligned=score >= 65 and direction != Direction.NONE and adx_now >= adx_min,
        weight=0.20,
    )
