"""Institutional multi-factor scoring engine."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from config import Settings
from src.analysis.fundamentals import analyze_fundamentals
from src.analysis.futures_metrics import analyze_futures_metrics
from src.analysis.momentum import analyze_momentum
from src.analysis.price_action import analyze_price_action
from src.analysis.smc import analyze_smc
from src.analysis.trend import analyze_trend, higher_tf_summary
from src.analysis.volume import analyze_volume
from src.models import NO_TRADE_MSG, Direction, FactorResult, SignalReport, Verdict
from src.risk import build_trade_levels

logger = logging.getLogger(__name__)

WEIGHTS = {
    "Trend": 0.25,
    "Momentum": 0.20,
    "Volume": 0.15,
    "Price Action": 0.15,
    "Smart Money Concepts": 0.15,
    "Futures Metrics": 0.05,
    "Fundamental Analysis": 0.05,
}


def _combine_direction(factors: list[FactorResult]) -> Direction:
    scores = {Direction.LONG: 0.0, Direction.SHORT: 0.0}
    for f in factors:
        if f.direction in (Direction.LONG, Direction.SHORT):
            scores[f.direction] += f.score * f.weight
    if scores[Direction.LONG] == scores[Direction.SHORT]:
        return Direction.NONE
    return max(scores, key=scores.get)


def _weighted_confidence(factors: list[FactorResult], direction: Direction) -> float:
    total_w = 0.0
    acc = 0.0
    for f in factors:
        w = f.weight
        total_w += w
        if f.direction == direction:
            acc += f.score * w
        elif f.direction == Direction.NONE:
            acc += f.score * w * 0.35
        else:
            # conflicting factor
            acc += (100 - f.score) * w * 0.15
    return round(acc / total_w if total_w else 0.0, 2)


def _verdict(direction: Direction, confidence: float, min_confidence: float = 80.0) -> Verdict:
    if direction == Direction.NONE or confidence < min_confidence:
        return Verdict.NO_TRADE if confidence < 70 else Verdict.WAIT
    if direction == Direction.LONG:
        return Verdict.STRONG_BUY if confidence >= 92 else Verdict.BUY
    return Verdict.STRONG_SELL if confidence >= 92 else Verdict.SELL


def _holding_time(tf_primary: str = "Min15") -> str:
    return {
        "Min15": "30m – 6h (scalp/intraday)",
        "Min60": "2h – 24h (intraday/swing)",
        "Hour4": "12h – 5d (swing)",
        "Day1": "3d – 3w (position)",
    }.get(tf_primary, "2h – 24h")


def analyze_symbol(
    symbol: str,
    frames: dict[str, pd.DataFrame],
    ticker: dict[str, Any] | None,
    deals: list[dict[str, Any]] | None,
    settings: Settings,
    fundamentals_cache: FactorResult | None = None,
) -> SignalReport:
    primary = frames.get("Min15")
    if primary is None or getattr(primary, "empty", False):
        primary = frames.get("Min60")
    factors: list[FactorResult] = [
        analyze_trend(frames),
        analyze_momentum(primary, adx_min=settings.adx_min),
        analyze_volume(primary, spike_mult=settings.volume_spike_mult),
        analyze_price_action(primary),
        analyze_smc(primary),
        analyze_futures_metrics(ticker, deals=deals),
        fundamentals_cache or analyze_fundamentals(settings.newsapi_key, symbol=symbol),
    ]

    # Enforce weights from spec
    for f in factors:
        f.weight = WEIGHTS.get(f.name, f.weight)

    direction = _combine_direction(factors)
    confidence = _weighted_confidence(factors, direction) if direction != Direction.NONE else _weighted_confidence(factors, Direction.LONG)

    missing = [f.name for f in factors if f.name in ("Trend", "Momentum", "Volume", "Price Action", "Smart Money Concepts") and not f.aligned]
    why: list[str] = []
    for f in factors:
        if f.direction == direction and f.aligned:
            why.extend(f.details[:2])

    htf = higher_tf_summary(frames)
    factor_scores = {f.name: round(f.score, 2) for f in factors}

    # Hard rejects
    reject_reasons: list[str] = []
    trend = next(f for f in factors if f.name == "Trend")
    fut = next(f for f in factors if f.name == "Futures Metrics")
    fund = next(f for f in factors if f.name == "Fundamental Analysis")

    if "conflicting higher-timeframe" in " ".join(trend.details).lower():
        reject_reasons.append("Conflicting higher-timeframe trends")
    if any("LOW LIQUIDITY" in d for d in fut.details) and not any(
        "Breakout" in d or "Breakdown" in d for d in next(f for f in factors if f.name == "Price Action").details
    ):
        reject_reasons.append("Low liquidity without clear breakout")
    if not fund.aligned and any("blackout" in d.lower() or "wait" in d.lower() for d in fund.details):
        reject_reasons.append("Major news / macro window within 30–60 minutes")
    if missing:
        reject_reasons.append(f"Missing key confirmations: {', '.join(missing)}")
    if direction == Direction.NONE:
        reject_reasons.append("No clear directional alignment across factors")

    levels = None
    if direction in (Direction.LONG, Direction.SHORT) and primary is not None:
        levels = build_trade_levels(
            primary,
            direction,
            account_balance=settings.account_balance_usdt,
            risk_pct=settings.risk_pct,
            min_rr=settings.min_rr,
            preferred_rr=settings.preferred_rr,
        )
        if levels is None:
            reject_reasons.append("Risk:Reward < 1:2.5 or stop beyond acceptable risk")

    if reject_reasons or confidence < settings.min_confidence or levels is None:
        verdict = Verdict.NO_TRADE if confidence < 70 else Verdict.WAIT
        return SignalReport(
            symbol=symbol,
            direction=Direction.NONE,
            confidence=confidence,
            verdict=verdict,
            message=NO_TRADE_MSG,
            why_valid=reject_reasons or ["Setup incomplete — multi-factor alignment failed"],
            higher_tf_trend=htf,
            levels=None,
            estimated_holding_time="",
            invalidation=["N/A — no active trade"],
            major_risks=reject_reasons,
            factor_scores=factor_scores,
            raw={"factors": {f.name: f.details for f in factors}},
        )

    invalidation = [
        f"Close beyond stop-loss at {levels.stop_loss}",
        "HTF EMA structure flips against trade",
        "Volume dries up and price re-enters prior range",
    ]
    risks = [
        "Funding squeeze / liquidation cascade",
        "Unexpected macro headline",
        "Exchange outage or thin book slippage",
    ]
    verdict = _verdict(direction, confidence, min_confidence=settings.min_confidence)

    return SignalReport(
        symbol=symbol,
        direction=direction,
        confidence=confidence,
        verdict=verdict,
        message="TRADE SETUP VALID",
        why_valid=why or ["Multi-factor confluence ≥ threshold"],
        higher_tf_trend=htf,
        levels=levels,
        estimated_holding_time=_holding_time("Min15"),
        invalidation=invalidation,
        major_risks=risks,
        factor_scores=factor_scores,
        raw={"factors": {f.name: f.details for f in factors}},
    )


def format_report(report: SignalReport) -> str:
    lines = [
        f"📊 *MEXC Futures Signal — {report.symbol}*",
        f"Verdict: *{report.verdict.value}*",
        f"Direction: *{report.direction.value}*",
        f"Confidence: *{report.confidence:.1f}%*",
        "",
        f"HTF trend: {report.higher_tf_trend}",
        "",
    ]
    if report.message == NO_TRADE_MSG or not report.is_actionable():
        lines.append(NO_TRADE_MSG)
        lines.append("")
        lines.append("Reasons:")
        for r in report.why_valid[:8]:
            lines.append(f"• {r}")
        lines.append("")
        lines.append("Factor scores:")
        for k, v in report.factor_scores.items():
            lines.append(f"• {k}: {v}")
        return "\n".join(lines)

    lv = report.levels
    assert lv is not None
    lines.extend(
        [
            "Why valid:",
            *[f"• {w}" for w in report.why_valid[:8]],
            "",
            f"Entry: `{lv.entry}`",
            f"Stop Loss: `{lv.stop_loss}`",
            f"TP1: `{lv.take_profit_1}`",
            f"TP2: `{lv.take_profit_2}`",
            f"TP3: `{lv.take_profit_3}`",
            f"Risk:Reward: *1:{lv.risk_reward}*",
            f"Position size (1% risk): `{lv.position_size}` (risk ${lv.risk_amount})",
            f"Est. holding time: {report.estimated_holding_time}",
            "",
            "Invalidation:",
            *[f"• {x}" for x in report.invalidation],
            "",
            "Major risks:",
            *[f"• {x}" for x in report.major_risks],
            "",
            "Factor scores:",
            *[f"• {k}: {v}" for k, v in report.factor_scores.items()],
            "",
            f"Final verdict: *{report.verdict.value}*",
        ]
    )
    return "\n".join(lines)
