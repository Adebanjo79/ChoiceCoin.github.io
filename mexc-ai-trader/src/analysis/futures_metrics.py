"""Futures market data: OI, funding, long/short proxy, CVD proxy, liquidity."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.models import Direction, FactorResult


def _cvd_from_deals(deals: list[dict[str, Any]]) -> tuple[float, str]:
    """Approximate CVD from recent trades (Taker side if available)."""
    if not deals:
        return 0.0, "CVD unavailable (no recent deals)"
    cvd = 0.0
    for d in deals:
        price = float(d.get("price") or d.get("p") or 0)
        vol = float(d.get("vol") or d.get("v") or d.get("amount") or 0)
        # MEXC: side/T 1=buy 2=sell (varies); also tradeSide
        side = d.get("side") or d.get("T") or d.get("tradeSide")
        notional = price * vol if price and vol else vol
        if side in (1, "1", "buy", "BUY", "bid"):
            cvd += notional
        elif side in (2, "2", "sell", "SELL", "ask"):
            cvd -= notional
        else:
            # unknown — skip
            continue
    if cvd > 0:
        return cvd, f"CVD proxy positive ({cvd:.2f}) — buy pressure"
    if cvd < 0:
        return cvd, f"CVD proxy negative ({cvd:.2f}) — sell pressure"
    return 0.0, "CVD proxy flat"


def analyze_futures_metrics(
    ticker: dict[str, Any] | None,
    deals: list[dict[str, Any]] | None = None,
    oi_history: pd.Series | None = None,
) -> FactorResult:
    details: list[str] = []
    bull = 0
    bear = 0
    checks = 0

    ticker = ticker or {}
    funding = float(ticker.get("fundingRate") or 0)
    hold_vol = float(ticker.get("holdVol") or 0)
    amount24 = float(ticker.get("amount24") or ticker.get("volume24") or 0)

    details.append(f"Funding rate: {funding:.6f}")
    details.append(f"Open interest (holdVol): {hold_vol:.2f}")
    details.append(f"24h turnover: {amount24:.2f}")

    # Funding: mildly positive with rising price can be crowded long; extreme = fade
    checks += 1
    if funding > 0.0005:
        bear += 1
        details.append("Elevated positive funding — crowded longs / SHORT bias risk")
    elif funding < -0.0005:
        bull += 1
        details.append("Negative funding — crowded shorts / LONG bias opportunity")
    else:
        details.append("Funding neutral")
        # neutral doesn't add direction

    # OI trend if provided
    checks += 1
    if oi_history is not None and len(oi_history) >= 3:
        slope = float(oi_history.iloc[-1] - oi_history.iloc[-3])
        if slope > 0:
            details.append("Open interest increasing")
            # OI up alone is directional-neutral; combine later with price in engine
            bull += 0.5
            bear += 0.5
        else:
            details.append("Open interest decreasing — trend may be weakening")
    else:
        details.append("OI historical trend limited to snapshot (ticker holdVol)")

    # Liquidity filter
    checks += 1
    low_liquidity = amount24 > 0 and amount24 < 500_000  # USDT turnover heuristic
    if low_liquidity:
        details.append("LOW LIQUIDITY — reject unless clear breakout confirmed elsewhere")
        # penalize both
        bull *= 0.5
        bear *= 0.5
    else:
        details.append("Liquidity OK for futures scan")
        bull += 0.25
        bear += 0.25

    # Long/short ratio proxy from bid/ask imbalance if present
    bid = float(ticker.get("bid1") or 0)
    ask = float(ticker.get("ask1") or 0)
    checks += 1
    if bid and ask:
        mid = (bid + ask) / 2
        spread_bps = (ask - bid) / mid * 10000
        details.append(f"Spread≈{spread_bps:.2f} bps (long/short book proxy via microprice)")
        if spread_bps > 15:
            details.append("Wide spread — cautious")
        else:
            bull += 0.25
            bear += 0.25
    else:
        details.append("Long/Short ratio: not published by MEXC public ticker — proxy only")

    # Liquidation heatmap — not available on public MEXC REST; note explicitly
    details.append("Liquidation heatmap: not available via public MEXC API (skipped)")

    cvd, cvd_msg = _cvd_from_deals(deals or [])
    details.append(cvd_msg)
    checks += 1
    if cvd > 0:
        bull += 1
    elif cvd < 0:
        bear += 1

    if bull > bear:
        direction = Direction.LONG
        score = min(100.0, (bull / max(checks, 1)) * 100 + 40)
    elif bear > bull:
        direction = Direction.SHORT
        score = min(100.0, (bear / max(checks, 1)) * 100 + 40)
    else:
        direction = Direction.NONE
        score = 45.0

    if low_liquidity:
        score = min(score, 40.0)

    return FactorResult(
        name="Futures Metrics",
        score=score,
        direction=direction,
        details=details,
        aligned=score >= 55 and direction != Direction.NONE and not low_liquidity,
        weight=0.05,
        # stash for engine
    )
