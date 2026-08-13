"""Risk management for spot: SL/TP, R:R filter, 1% size, optional ~50% upside TP3."""

from __future__ import annotations

import pandas as pd

from src.indicators.technical import atr, swing_points
from src.models import Direction, TradeLevels


def build_trade_levels(
    df: pd.DataFrame,
    direction: Direction,
    account_balance: float,
    risk_pct: float = 0.01,
    min_rr: float = 2.5,
    preferred_rr: float = 3.0,
    target_upside_pct: float = 50.0,
    max_stop_pct: float = 0.08,
    clamp_stop: bool = False,
) -> TradeLevels | None:
    """
    Spot-focused levels.

    For LONG (spot BUY): TP1/TP2 follow R-multiples; TP3 aims toward
    ``target_upside_pct`` price gain (default 50%) when R:R still clears min_rr.
    For SHORT (spot SELL/exit): classic R-multiples only.
    """
    if df is None or len(df) < 30 or direction not in (Direction.LONG, Direction.SHORT):
        return None

    entry = float(df["close"].iloc[-1])
    atr_val = float(atr(df, 14).iloc[-1])
    hi_idx, _ = swing_points(df["high"], 2, 2)
    _, lo_idx = swing_points(df["low"], 2, 2)

    if direction == Direction.LONG:
        structure_sl = float(df["low"].iloc[lo_idx[-1]]) if lo_idx else entry - 1.5 * atr_val
        stop = min(structure_sl, entry - 1.0 * atr_val) * 0.999
        risk = entry - stop
        if risk <= 0:
            return None
        tp1 = entry + risk * 1.5
        tp2 = entry + risk * preferred_rr
        # Prefer ~50% price upside for TP3 when R:R to that level still clears min_rr
        stretch = entry * (1.0 + max(target_upside_pct, 0.0) / 100.0)
        stretch_rr = (stretch - entry) / risk if risk else 0.0
        if stretch > tp2 and stretch_rr >= min_rr:
            tp3 = stretch
        else:
            tp3 = entry + risk * max(preferred_rr, 5.0)
            tp3 = max(tp3, tp2)
        rr = (tp2 - entry) / risk
        upside_to_tp3 = (tp3 - entry) / entry * 100.0
    else:
        structure_sl = float(df["high"].iloc[hi_idx[-1]]) if hi_idx else entry + 1.5 * atr_val
        stop = max(structure_sl, entry + 1.0 * atr_val) * 1.001
        risk = stop - entry
        if risk <= 0:
            return None
        tp1 = entry - risk * 1.5
        tp2 = entry - risk * preferred_rr
        tp3 = entry - risk * max(preferred_rr, 4.0)
        rr = (entry - tp2) / risk
        upside_to_tp3 = (entry - tp3) / entry * 100.0

    if rr < min_rr:
        return None

    # Reject absurd stop as unacceptable risk distance — unless clamp_stop
    if risk / entry > max_stop_pct:
        if not clamp_stop:
            return None
        # Cap stop distance so alt breakouts can still alert with defined risk
        if direction == Direction.LONG:
            stop = entry * (1.0 - max_stop_pct)
            risk = entry - stop
            tp1 = entry + risk * 1.5
            tp2 = entry + risk * preferred_rr
            stretch = entry * (1.0 + max(target_upside_pct, 0.0) / 100.0)
            tp3 = max(tp2, stretch)
            rr = (tp2 - entry) / risk if risk else 0.0
            upside_to_tp3 = (tp3 - entry) / entry * 100.0
        else:
            stop = entry * (1.0 + max_stop_pct)
            risk = stop - entry
            tp1 = entry - risk * 1.5
            tp2 = entry - risk * preferred_rr
            tp3 = entry - risk * max(preferred_rr, 4.0)
            rr = (entry - tp2) / risk if risk else 0.0
            upside_to_tp3 = (entry - tp3) / entry * 100.0
        if risk <= 0 or rr < min_rr:
            return None

    risk_amount = account_balance * risk_pct
    position_size = risk_amount / risk if risk else 0.0  # coin units
    position_notional = position_size * entry

    # Cap notional at account balance for spot (no leverage)
    if position_notional > account_balance and entry > 0:
        position_size = account_balance / entry
        position_notional = account_balance

    return TradeLevels(
        entry=round(entry, 8),
        stop_loss=round(stop, 8),
        take_profit_1=round(tp1, 8),
        take_profit_2=round(tp2, 8),
        take_profit_3=round(tp3, 8),
        risk_reward=round(rr, 2),
        position_size=round(position_size, 6),
        risk_amount=round(risk_amount, 4),
        position_notional=round(position_notional, 4),
        upside_pct_tp3=round(upside_to_tp3, 2),
    )
