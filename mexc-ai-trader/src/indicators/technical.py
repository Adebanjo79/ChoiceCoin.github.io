"""Technical indicator helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    # Avoid NaN when there are no losses (strong uptrend) or no gains
    rs = pd.Series(np.where(avg_loss == 0, np.inf, avg_gain / avg_loss), index=series.index)
    out = 100 - (100 / (1 + rs))
    return out.replace([np.inf, -np.inf], np.nan).fillna(100.0)


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    line = ema_fast - ema_slow
    sig = ema(line, signal)
    hist = line - sig
    return pd.DataFrame({"macd": line, "signal": sig, "hist": hist})


def stochastic_rsi(
    series: pd.Series, rsi_len: int = 14, stoch_len: int = 14, k: int = 3, d: int = 3
) -> pd.DataFrame:
    r = rsi(series, rsi_len)
    lowest = r.rolling(stoch_len).min()
    highest = r.rolling(stoch_len).max()
    stoch = (r - lowest) / (highest - lowest).replace(0, np.nan)
    k_line = stoch.rolling(k).mean() * 100
    d_line = k_line.rolling(d).mean()
    return pd.DataFrame({"k": k_line, "d": d_line})


def adx(df: pd.DataFrame, length: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = tr.ewm(alpha=1 / length, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1 / length, adjust=False).mean() / atr.replace(0, np.nan))
    minus_di = 100 * (minus_dm.ewm(alpha=1 / length, adjust=False).mean() / atr.replace(0, np.nan))
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    return dx.ewm(alpha=1 / length, adjust=False).mean()


def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / length, adjust=False).mean()


def obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["close"].diff()).fillna(0)
    return (direction * df["volume"]).cumsum()


def cmf(df: pd.DataFrame, length: int = 20) -> pd.Series:
    high, low, close, vol = df["high"], df["low"], df["close"], df["volume"]
    mfm = ((close - low) - (high - close)) / (high - low).replace(0, np.nan)
    mfv = mfm * vol
    return mfv.rolling(length).sum() / vol.rolling(length).sum().replace(0, np.nan)


def volume_profile_nodes(df: pd.DataFrame, bins: int = 24) -> dict[str, float]:
    """Approximate HVN/LVN from recent closes weighted by volume."""
    if df.empty or df["volume"].sum() <= 0:
        return {"hvn": float("nan"), "lvn": float("nan"), "poc": float("nan")}
    prices = df["close"].to_numpy()
    vols = df["volume"].to_numpy()
    hist, edges = np.histogram(prices, bins=bins, weights=vols)
    centers = (edges[:-1] + edges[1:]) / 2
    poc = float(centers[int(np.argmax(hist))])
    hvn = float(centers[int(np.argmax(hist))])
    lvn = float(centers[int(np.argmin(hist))])
    return {"hvn": hvn, "lvn": lvn, "poc": poc}


def swing_points(series: pd.Series, left: int = 2, right: int = 2) -> tuple[list[int], list[int]]:
    highs: list[int] = []
    lows: list[int] = []
    values = series.to_numpy()
    n = len(values)
    for i in range(left, n - right):
        window = values[i - left : i + right + 1]
        if values[i] == np.max(window) and np.sum(window == values[i]) == 1:
            highs.append(i)
        if values[i] == np.min(window) and np.sum(window == values[i]) == 1:
            lows.append(i)
    return highs, lows
