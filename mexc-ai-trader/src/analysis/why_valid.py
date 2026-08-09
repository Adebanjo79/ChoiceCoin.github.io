"""FutureTradeBot-style "Why valid" checklist from primary timeframe OHLCV."""

from __future__ import annotations

import pandas as pd

from src.indicators.technical import ema, macd, obv, rsi
from src.models import Direction


def _fmt_px(x: float) -> str:
    ax = abs(float(x))
    if ax >= 1000:
        return f"{x:.2f}"
    if ax >= 1:
        return f"{x:.4f}"
    if ax >= 0.01:
        return f"{x:.6f}"
    s = f"{x:.8f}".rstrip("0").rstrip(".")
    return s or "0"


def _rsi_div_label(close: pd.Series, rsi_series: pd.Series, lookback: int = 30) -> str:
    if len(close) < lookback + 5:
        return "none divergence"
    c = close.iloc[-lookback:]
    r = rsi_series.iloc[-lookback:]
    price_ll = c.iloc[-1] < c.min() * 1.001 and c.iloc[-1] <= c.iloc[:-3].min()
    price_hh = c.iloc[-1] > c.max() * 0.999 and c.iloc[-1] >= c.iloc[:-3].max()
    rsi_hl = r.iloc[-1] > r.iloc[:-3].min()
    rsi_lh = r.iloc[-1] < r.iloc[:-3].max()
    if price_ll and rsi_hl:
        return "bullish divergence"
    if price_hh and rsi_lh:
        return "bearish divergence"
    return "none divergence"


def build_why_valid(primary: pd.DataFrame | None, direction: Direction) -> list[str]:
    """Build PEPE-style Why valid bullets for LONG/SHORT alerts.

    Matches FutureTradeBot cards:
      • EMA stack bullish (9/20/50/100/200)
      • Price above EMA200 (...)
      • RSI(14)=69.4 (none divergence)
      • MACD hist ... · bullish
      • Volume 1.32x 20-SMA (>=1.3x OK)
      • OBV rising
      • Not in tight consolidation
      • S/R window: Support ... / Resistance ...
    """
    if direction not in (Direction.LONG, Direction.SHORT):
        return []
    if primary is None or len(primary) < 210:
        return []

    long = direction == Direction.LONG
    close = primary["close"]
    high = primary["high"]
    low = primary["low"]
    volume = primary["volume"]
    price = float(close.iloc[-1])

    e9 = float(ema(close, 9).iloc[-1])
    e20 = float(ema(close, 20).iloc[-1])
    e50 = float(ema(close, 50).iloc[-1])
    e100 = float(ema(close, 100).iloc[-1])
    e200 = float(ema(close, 200).iloc[-1])

    bull_stack = e9 > e20 > e50 > e100 > e200
    bear_stack = e9 < e20 < e50 < e100 < e200
    stack_ok = bull_stack if long else bear_stack
    stack_txt = "bullish" if long else "bearish"
    stack_line = (
        f"EMA stack {stack_txt} (9/20/50/100/200)"
        if stack_ok
        else f"EMA stack mixed (want {stack_txt} 9/20/50/100/200)"
    )

    if long:
        ema200_line = (
            f"Price above EMA200 ({_fmt_px(e200)})"
            if price > e200
            else f"Price not above EMA200 ({_fmt_px(e200)})"
        )
    else:
        ema200_line = (
            f"Price below EMA200 ({_fmt_px(e200)})"
            if price < e200
            else f"Price not below EMA200 ({_fmt_px(e200)})"
        )

    r = rsi(close, 14)
    rsi_v = float(r.iloc[-1])
    div = _rsi_div_label(close, r)
    rsi_line = f"RSI(14)={rsi_v:.1f} ({div})"

    m = macd(close)
    hist = float(m["hist"].iloc[-1])
    hist_prev = float(m["hist"].iloc[-2])
    macd_bull = hist > 0 and hist >= hist_prev
    macd_bear = hist < 0 and hist <= hist_prev
    if long:
        macd_side = "bullish" if macd_bull or hist > 0 else "bearish"
    else:
        macd_side = "bearish" if macd_bear or hist < 0 else "bullish"
    macd_line = f"MACD hist {_fmt_px(hist)} · {macd_side}"

    avg20 = float(volume.iloc[-21:-1].mean()) if len(volume) >= 21 else 0.0
    cur_vol = float(volume.iloc[-1])
    vr = (cur_vol / avg20) if avg20 > 0 else 0.0
    vol_ok = vr >= 1.3
    vol_line = f"Volume {vr:.2f}x 20-SMA ({'>=1.3x OK' if vol_ok else '<1.3x weak'})"

    obv_s = obv(primary)
    obv_rising = float(obv_s.iloc[-1] - obv_s.iloc[-6]) > 0
    obv_line = "OBV rising" if obv_rising else "OBV flat/falling"

    window = close.iloc[-20:]
    mid = float(window.mean())
    tight = ((float(window.max()) - float(window.min())) / mid) < 0.012 if mid else True
    consol_line = "In tight consolidation" if tight else "Not in tight consolidation"

    look = min(40, len(high), len(low))
    support = float(low.iloc[-look:].min())
    resistance = float(high.iloc[-look:].max())
    sr_line = f"S/R window: Support {_fmt_px(support)} / Resistance {_fmt_px(resistance)}"

    return [
        stack_line,
        ema200_line,
        rsi_line,
        macd_line,
        vol_line,
        obv_line,
        consol_line,
        sr_line,
    ]
