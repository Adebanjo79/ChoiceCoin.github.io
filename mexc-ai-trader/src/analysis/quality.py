"""Extra quality gates for lower confidence thresholds (e.g. 70%)."""

from __future__ import annotations

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


def volume_above_avg(
    df: pd.DataFrame | None,
    length: int = 20,
    min_mult: float = 1.0,
) -> tuple[bool, str]:
    """FutureTradeBot-style: require volume >= min_mult × 20-SMA (default 1.3x when gated)."""
    if df is None or len(df) < length + 2:
        return False, "Volume check failed (insufficient data)"
    avg = float(df["volume"].iloc[-(length + 1) : -1].mean())
    cur = float(df["volume"].iloc[-1])
    if avg <= 0:
        return False, "Volume check failed (zero average)"
    ratio = cur / avg
    ok = ratio >= min_mult
    tag = f">={min_mult:.1f}x OK" if ok else f"<{min_mult:.1f}x weak"
    return ok, f"Volume {ratio:.2f}x {length}-SMA ({tag})"


def apply_quality_filters(
    *,
    primary: pd.DataFrame | None,
    fund_details: list[str],
    btc_volatility_pct: float | None,
    max_btc_volatility_pct: float,
    require_volume_above_avg: bool,
    volume_min_mult: float = 1.3,
) -> list[str]:
    """Return reject reasons (empty list means pass)."""
    rejects: list[str] = []

    # Hard news block only (keyword blackout). Soft UTC windows no longer hard-reject.
    joined = " ".join(fund_details).lower()
    if "blackout" in joined and "major news keywords" in joined:
        rejects.append("News/macro blackout — skip trade")
    if "fundamental blackout" in joined:
        rejects.append("Fundamental blackout — skip trade")

    # Volume >= N× 20-period SMA (FutureTradeBot uses 1.3x)
    if require_volume_above_avg:
        ok, msg = volume_above_avg(primary, 20, min_mult=volume_min_mult)
        if not ok:
            rejects.append(msg)

    # BTC volatility: only reject when we HAVE a reading and it is too high
    if btc_volatility_pct is not None and btc_volatility_pct > max_btc_volatility_pct:
        rejects.append(
            f"BTC volatility {btc_volatility_pct:.2f}% > max {max_btc_volatility_pct:.2f}% — too choppy"
        )

    return rejects
