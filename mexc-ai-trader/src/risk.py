"""Risk management: SL/TP levels, R:R filter, 1% position sizing."""

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
    preferred_rr: float = 2.5,
    rr_tp1: float = 2.0,
    rr_tp2: float = 2.5,
    rr_tp3: float = 3.5,
) -> TradeLevels | None:
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
        tp1 = entry + risk * rr_tp1
        tp2 = entry + risk * rr_tp2
        tp3 = entry + risk * rr_tp3
        rr = (tp2 - entry) / risk
    else:
        structure_sl = float(df["high"].iloc[hi_idx[-1]]) if hi_idx else entry + 1.5 * atr_val
        stop = max(structure_sl, entry + 1.0 * atr_val) * 1.001
        risk = stop - entry
        if risk <= 0:
            return None
        tp1 = entry - risk * rr_tp1
        tp2 = entry - risk * rr_tp2
        tp3 = entry - risk * rr_tp3
        rr = (entry - tp2) / risk

    if rr < min_rr:
        return None

    risk_amount = account_balance * risk_pct
    position_size = risk_amount / risk if risk else 0.0

    if risk / entry > 0.08:
        return None

    return TradeLevels(
        entry=round(entry, 8),
        stop_loss=round(stop, 8),
        take_profit_1=round(tp1, 8),
        take_profit_2=round(tp2, 8),
        take_profit_3=round(tp3, 8),
        risk_reward=round(rr, 2),
        position_size=round(position_size, 6),
        risk_amount=round(risk_amount, 4),
        rr_tp1=rr_tp1,
        rr_tp2=rr_tp2,
        rr_tp3=rr_tp3,
    )
