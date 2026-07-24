"""Spot market data: liquidity, order-book pressure, CVD proxy (no funding/OI)."""

from __future__ import annotations

from typing import Any

from src.models import Direction, FactorResult


def _cvd_from_trades(trades: list[dict[str, Any]]) -> tuple[float, str]:
    """Approximate CVD from recent spot trades."""
    if not trades:
        return 0.0, "CVD unavailable (no recent trades)"
    cvd = 0.0
    for t in trades:
        price = float(t.get("price") or 0)
        qty = float(t.get("qty") or t.get("quantity") or t.get("vol") or 0)
        notional = price * qty if price and qty else qty
        # MEXC spot: isBuyerMaker True => seller aggressor (sell), False => buyer aggressor (buy)
        is_buyer_maker = t.get("isBuyerMaker")
        side = t.get("side") or t.get("tradeType")
        if is_buyer_maker is True or side in (2, "2", "SELL", "sell", "ASK"):
            cvd -= notional
        elif is_buyer_maker is False or side in (1, "1", "BUY", "buy", "BID"):
            cvd += notional
        else:
            continue
    if cvd > 0:
        return cvd, f"CVD proxy positive ({cvd:.2f}) — buy pressure"
    if cvd < 0:
        return cvd, f"CVD proxy negative ({cvd:.2f}) — sell pressure"
    return 0.0, "CVD proxy flat"


def analyze_spot_metrics(
    ticker: dict[str, Any] | None,
    trades: list[dict[str, Any]] | None = None,
    depth: dict[str, Any] | None = None,
) -> FactorResult:
    details: list[str] = []
    bull = 0.0
    bear = 0.0
    checks = 0

    ticker = ticker or {}
    quote_vol = float(
        ticker.get("quoteVolume")
        or ticker.get("amount24")
        or ticker.get("volume24")
        or 0
    )
    last = float(ticker.get("lastPrice") or ticker.get("last") or 0)
    bid = float(ticker.get("bidPrice") or ticker.get("bid1") or 0)
    ask = float(ticker.get("askPrice") or ticker.get("ask1") or 0)
    change_pct = float(ticker.get("priceChangePercent") or ticker.get("riseFallRate") or 0)
    # riseFallRate on futures was fraction; spot percent may already be %
    if abs(change_pct) < 1 and "priceChangePercent" not in ticker:
        change_pct *= 100

    details.append(f"Last price: {last}")
    details.append(f"24h quote turnover: {quote_vol:.2f} USDT")
    details.append(f"24h change: {change_pct:.2f}%")

    checks += 1
    low_liquidity = quote_vol > 0 and quote_vol < 300_000
    if low_liquidity:
        details.append("LOW LIQUIDITY — reject unless clear breakout confirmed elsewhere")
        bull *= 0.5
        bear *= 0.5
    else:
        details.append("Spot liquidity OK")
        bull += 0.35
        bear += 0.35

    checks += 1
    if bid and ask and last:
        mid = (bid + ask) / 2
        spread_bps = (ask - bid) / mid * 10000 if mid else 0
        details.append(f"Spread ≈ {spread_bps:.2f} bps")
        if spread_bps > 25:
            details.append("Wide spot spread — cautious")
            bear += 0.25
        else:
            details.append("Tight book — OK for spot entry")
            bull += 0.35
            bear += 0.15
    else:
        details.append("Book ticker incomplete")

    # Order-book imbalance from depth if present
    checks += 1
    if depth and isinstance(depth, dict):
        bids = depth.get("bids") or []
        asks = depth.get("asks") or []
        bid_notional = 0.0
        ask_notional = 0.0
        for b in bids[:20]:
            try:
                bid_notional += float(b[0]) * float(b[1])
            except (TypeError, ValueError, IndexError):
                pass
        for a in asks[:20]:
            try:
                ask_notional += float(a[0]) * float(a[1])
            except (TypeError, ValueError, IndexError):
                pass
        total = bid_notional + ask_notional
        if total > 0:
            imbalance = (bid_notional - ask_notional) / total
            details.append(f"Book imbalance (top20): {imbalance:+.2%}")
            if imbalance > 0.12:
                bull += 1
                details.append("Bid-heavy book — spot BUY support")
            elif imbalance < -0.12:
                bear += 1
                details.append("Ask-heavy book — spot SELL pressure")
            else:
                details.append("Balanced spot book")
        else:
            details.append("Depth empty — skipped")
    else:
        details.append("Order-book depth not fetched this cycle")

    # Spot has no funding / OI / liquidation heatmap
    details.append("Funding / OI / liquidation heatmap: N/A on spot (skipped)")

    cvd, cvd_msg = _cvd_from_trades(trades or [])
    details.append(cvd_msg)
    checks += 1
    if cvd > 0:
        bull += 1
    elif cvd < 0:
        bear += 1

    # Mild momentum tilt from 24h change (spot swing context)
    checks += 1
    if change_pct >= 3:
        bull += 0.5
        details.append("Positive 24h momentum supports spot longs")
    elif change_pct <= -3:
        bear += 0.5
        details.append("Negative 24h momentum — caution on new buys")
    else:
        details.append("24h momentum neutral")

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
        name="Spot Metrics",
        score=score,
        direction=direction,
        details=details,
        aligned=score >= 55 and direction != Direction.NONE and not low_liquidity,
        weight=0.05,
    )


# Alias so older engine imports keep working during transition
analyze_futures_metrics = analyze_spot_metrics
