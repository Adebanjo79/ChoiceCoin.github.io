"""Shared data models for analysis results and trade signals."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"


class Verdict(str, Enum):
    STRONG_BUY = "STRONG BUY"
    BUY = "BUY"
    WAIT = "WAIT"
    SELL = "SELL"
    STRONG_SELL = "STRONG SELL"
    NO_TRADE = "NO TRADE"


NO_TRADE_MSG = "NO TRADE – WAIT FOR BETTER CONFIRMATION."


@dataclass
class FactorResult:
    name: str
    score: float  # 0-100
    direction: Direction
    details: list[str] = field(default_factory=list)
    aligned: bool = False
    weight: float = 0.0


@dataclass
class TradeLevels:
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    risk_reward: float
    position_size: float
    risk_amount: float
    rr_tp1: float = 2.0
    rr_tp2: float = 2.5
    rr_tp3: float = 3.5


@dataclass
class SignalReport:
    symbol: str
    direction: Direction
    confidence: float
    verdict: Verdict
    message: str
    why_valid: list[str] = field(default_factory=list)
    higher_tf_trend: str = ""
    levels: TradeLevels | None = None
    estimated_holding_time: str = ""
    invalidation: list[str] = field(default_factory=list)
    major_risks: list[str] = field(default_factory=list)
    factor_scores: dict[str, float] = field(default_factory=dict)
    factor_aligned: dict[str, bool] = field(default_factory=dict)
    factor_weights: dict[str, float] = field(default_factory=dict)
    price: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def is_actionable(self) -> bool:
        return self.verdict in {
            Verdict.STRONG_BUY,
            Verdict.BUY,
            Verdict.SELL,
            Verdict.STRONG_SELL,
        } and self.direction in {Direction.LONG, Direction.SHORT}

    def side_label(self) -> str:
        if self.direction == Direction.LONG:
            return "BUY · LONG"
        if self.direction == Direction.SHORT:
            return "SELL · SHORT"
        return "NO TRADE"
