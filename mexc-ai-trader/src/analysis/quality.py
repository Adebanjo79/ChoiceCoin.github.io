"""Extra quality gates for lower confidence thresholds (e.g. 70%)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.indicators.technical import atr


def btc_atr_pct(btc_df: pd.DataFrame | None) -> float | None:
    """BTC ATR(14) as % of price (15m/primary BTC frame)."""
    if btc_df is None or len(btc_df) < 30:
        return None
    atr_val = float(atr(btc_df, 14).iloc[-1])
    price = float(btc_df["close"].iloc[-1])
    if price <= 0:
        return None
    return (atr_val / price) * 100.0


def volume_above_avg(df: pd.DataFrame | None, length: int = 20) -> tuple[bool, str]:
    if df is None or len(df) < length + 2:
        return False, "Volume check failed (insufficient data)"
    avg = float(df["volume"].iloc[-(length + 1) : -1].mean())
    cur = float(df["volume"].iloc[-1])
    if avg <= 0:
        return False, "Volume check failed (zero average)"
    ok = cur > avg
    return ok, f"Volume {cur:.2f} vs {length}-avg {avg:.2f} ({'OK' if ok else 'TOO LOW'})"


def apply_quality_filters(
    *,
    primary: pd.DataFrame | None,
    fund_details: list[str],
    btc_volatility_pct: float | None,
    max_btc_volatility_pct: float,
    require_volume_above_avg: bool,
) -> list[str]:
    """Return reject reasons (empty list means pass)."""
    rejects: list[str] = []

    # Not news / macro time
    joined = " ".join(fund_details).lower()
    if "blackout" in joined or "wait 30–60" in joined or "wait 30-60" in joined:
        rejects.append("News/macro window active — skip trade")
    if "soft macro release window" in joined:
        rejects.append("Macro release window — skip trade")

    # Volume > 20-period average
    if require_volume_above_avg:
        ok, msg = volume_above_avg(primary, 20)
        if not ok:
            rejects.append(msg)

    # BTC volatility must stay below threshold (avoid chop)
    if btc_volatility_pct is None:
        rejects.append("BTC volatility unavailable — skip for safety")
    elif btc_volatility_pct > max_btc_volatility_pct:
        rejects.append(
            f"BTC volatility {btc_volatility_pct:.2f}% > max {max_btc_volatility_pct:.2f}% — too choppy"
        )

    return rejects
