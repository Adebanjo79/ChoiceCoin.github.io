"""Institutional multi-factor scoring engine — MEXC Spot."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from config import Settings
from src.analysis.fundamentals import analyze_fundamentals
from src.analysis.momentum import analyze_momentum
from src.analysis.price_action import analyze_price_action
from src.analysis.quality import apply_quality_filters, btc_atr_pct
from src.analysis.smc import analyze_smc
from src.analysis.spot_metrics import analyze_spot_metrics
from src.analysis.trend import analyze_trend, higher_tf_summary
from src.analysis.volume import analyze_volume
from src.mexc_client import display_symbol
from src.models import NO_TRADE_MSG, Direction, FactorResult, SignalReport, Verdict
from src.risk import build_trade_levels

logger = logging.getLogger(__name__)

KEY_FACTORS = ("Trend", "Momentum", "Volume", "Price Action", "Smart Money Concepts")

WEIGHTS = {
    "Trend": 0.25,
    "Momentum": 0.20,
    "Volume": 0.15,
    "Price Action": 0.15,
    "Smart Money Concepts": 0.15,
    "Spot Metrics": 0.05,
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
            acc += (100 - f.score) * w * 0.15
    return round(acc / total_w if total_w else 0.0, 2)


def _verdict(direction: Direction, confidence: float, min_confidence: float = 70.0) -> Verdict:
    if direction == Direction.NONE or confidence < min_confidence:
        return Verdict.NO_TRADE if confidence < 70 else Verdict.WAIT
    if direction == Direction.LONG:
        return Verdict.STRONG_BUY if confidence >= 92 else Verdict.BUY
    return Verdict.STRONG_SELL if confidence >= 92 else Verdict.SELL


def _holding_time(tf_primary: str = "Min15") -> str:
    return {
        "Min15": "30m – 6h (scalp/intraday spot)",
        "Min60": "2h – 24h (intraday/swing spot)",
        "Hour4": "12h – 5d (swing spot)",
        "Day1": "3d – 3w (position spot)",
    }.get(tf_primary, "2h – 24h spot")


def analyze_symbol(
    symbol: str,
    frames: dict[str, pd.DataFrame],
    ticker: dict[str, Any] | None,
    deals: list[dict[str, Any]] | None,
    settings: Settings,
    fundamentals_cache: FactorResult | None = None,
    btc_df: pd.DataFrame | None = None,
    depth: dict[str, Any] | None = None,
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
        analyze_spot_metrics(ticker, trades=deals, depth=depth),
        fundamentals_cache or analyze_fundamentals(settings.newsapi_key, symbol=symbol),
    ]

    for f in factors:
        f.weight = WEIGHTS.get(f.name, f.weight)

    direction = _combine_direction(factors)
    confidence = (
        _weighted_confidence(factors, direction)
        if direction != Direction.NONE
        else _weighted_confidence(factors, Direction.LONG)
    )

    aligned_keys = [f.name for f in factors if f.name in KEY_FACTORS and f.aligned]
    missing = [name for name in KEY_FACTORS if name not in aligned_keys]
    why: list[str] = []
    for f in factors:
        if f.direction == direction and f.aligned:
            why.extend(f.details[:2])

    htf = higher_tf_summary(frames)
    factor_scores = {f.name: round(f.score, 2) for f in factors}

    reject_reasons: list[str] = []
    trend = next(f for f in factors if f.name == "Trend")
    spot = next(f for f in factors if f.name == "Spot Metrics")
    fund = next(f for f in factors if f.name == "Fundamental Analysis")

    if "conflicting higher-timeframe" in " ".join(trend.details).lower():
        reject_reasons.append("Conflicting higher-timeframe trends")
    if any("LOW LIQUIDITY" in d for d in spot.details) and not any(
        "Breakout" in d or "Breakdown" in d for d in next(f for f in factors if f.name == "Price Action").details
    ):
        reject_reasons.append("Low liquidity without clear breakout")
    if not fund.aligned and any("blackout" in d.lower() or "wait" in d.lower() for d in fund.details):
        reject_reasons.append("Major news / macro window within 30–60 minutes")

    min_aligned = getattr(settings, "min_aligned_factors", 2)
    if len(aligned_keys) < min_aligned:
        reject_reasons.append(
            f"Only {len(aligned_keys)}/{len(KEY_FACTORS)} key factors aligned (need {min_aligned})"
        )

    if getattr(settings, "quality_filters", True):
        btc_vol = btc_atr_pct(btc_df)
        q_rejects = apply_quality_filters(
            primary=primary,
            fund_details=fund.details,
            btc_volatility_pct=btc_vol,
            max_btc_volatility_pct=settings.max_btc_volatility_pct,
            require_volume_above_avg=settings.require_volume_above_avg,
        )
        reject_reasons.extend(q_rejects)
        if btc_vol is not None:
            why.append(f"BTC ATR%={btc_vol:.2f} (max {settings.max_btc_volatility_pct:.2f})")

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
            target_upside_pct=settings.target_upside_pct,
            max_stop_pct=settings.max_stop_pct,
        )
        if levels is None:
            reject_reasons.append("Risk:Reward < 1:2.5 or stop beyond acceptable risk")

    if reject_reasons or confidence < settings.min_confidence or levels is None:
        verdict = Verdict.NO_TRADE if confidence < settings.min_confidence else Verdict.WAIT
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
            trade_style="SPOT",
            raw={"factors": {f.name: f.details for f in factors}, "missing": missing},
        )

    invalidation = [
        f"Close beyond stop-loss at {levels.stop_loss}",
        "HTF EMA structure flips against trade",
        "Volume dries up and price re-enters prior range",
    ]
    risks = [
        "Spot gap / sudden dump (no futures liquidation cascade, but thin books still slip)",
        "Unexpected macro headline",
        "Exchange outage or thin book slippage",
        f"Account is {settings.account_balance_usdt:.0f} USDT — size carefully; TP3 ~{settings.target_upside_pct:.0f}% is ambitious on majors",
    ]
    verdict = _verdict(direction, confidence, min_confidence=settings.min_confidence)

    return SignalReport(
        symbol=symbol,
        direction=direction,
        confidence=confidence,
        verdict=verdict,
        message="SPOT TRADE SETUP VALID",
        why_valid=why or ["Multi-factor confluence ≥ threshold"],
        higher_tf_trend=htf,
        levels=levels,
        estimated_holding_time=_holding_time("Min15"),
        invalidation=invalidation,
        major_risks=risks,
        factor_scores=factor_scores,
        trade_style="SPOT",
        raw={"factors": {f.name: f.details for f in factors}},
    )


def format_report(report: SignalReport) -> str:
    shown = display_symbol(report.symbol)
    lines = [
        f"📊 MEXC SPOT Signal — {shown}",
        f"Verdict: {report.verdict.value}",
        f"Trade direction (spot): {report.spot_side_label()}",
        f"Confidence: {report.confidence:.1f}%",
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
    pot_gain = lv.position_notional * (lv.upside_pct_tp3 / 100.0) if lv.position_notional else 0.0
    lines.extend(
        [
            "Why the trade is valid:",
            *[f"• {w}" for w in report.why_valid[:8]],
            "",
            f"Entry: {lv.entry}",
            f"Stop Loss: {lv.stop_loss}",
            f"Take Profit 1: {lv.take_profit_1}",
            f"Take Profit 2: {lv.take_profit_2}",
            f"Take Profit 3: {lv.take_profit_3} (~{lv.upside_pct_tp3:.1f}% price move)",
            f"Risk:Reward: 1:{lv.risk_reward}",
            f"Position size (1% risk): {lv.position_size} coins ≈ {lv.position_notional:.2f} USDT",
            f"Risk amount: ${lv.risk_amount}",
            f"If TP3 hits (approx): +{pot_gain:.2f} USDT on this size",
            f"Est. holding time: {report.estimated_holding_time}",
            "",
            "Trade invalidation:",
            *[f"• {x}" for x in report.invalidation],
            "",
            "Major risks:",
            *[f"• {x}" for x in report.major_risks],
            "",
            "Factor scores:",
            *[f"• {k}: {v}" for k, v in report.factor_scores.items()],
            "",
            f"Final verdict: {report.verdict.value}",
        ]
    )
    return "\n".join(lines)
