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
from src.analysis.quality import apply_quality_filters, btc_atr_pct
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
        "Min15": "2h – 12h",
        "Min60": "4h – 24h",
        "Hour4": "12h – 5d",
        "Day1": "3d – 3w",
    }.get(tf_primary, "2h – 12h")


def analyze_symbol(
    symbol: str,
    frames: dict[str, pd.DataFrame],
    ticker: dict[str, Any] | None,
    deals: list[dict[str, Any]] | None,
    settings: Settings,
    fundamentals_cache: FactorResult | None = None,
    btc_df: pd.DataFrame | None = None,
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

    aligned_keys = [f.name for f in factors if f.name in KEY_FACTORS and f.aligned]
    missing = [name for name in KEY_FACTORS if name not in aligned_keys]
    why: list[str] = []
    for f in factors:
        # Pull concrete checklist lines for the FutureTradeBot-style "Why valid"
        if f.direction == direction or f.aligned:
            why.extend(f.details[:3])
    # Deduplicate while preserving order
    seen: set[str] = set()
    why = [w for w in why if not (w in seen or seen.add(w))][:10]

    htf = higher_tf_summary(frames)
    factor_scores = {f.name: round(f.score, 2) for f in factors}
    factor_aligned = {f.name: bool(f.aligned) for f in factors}
    factor_weights = {f.name: float(f.weight) for f in factors}
    price = float(primary["close"].iloc[-1]) if primary is not None and len(primary) else None

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
    if any("fundamental blackout" in d.lower() for d in fund.details) or (
        any("major news keywords" in d.lower() for d in fund.details)
    ):
        reject_reasons.append("Major news keywords active — skip trade")

    # Require a minimum number of aligned pillars (default 2) instead of all five
    min_aligned = getattr(settings, "min_aligned_factors", 2)
    if len(aligned_keys) < min_aligned:
        reject_reasons.append(
            f"Only {len(aligned_keys)}/{len(KEY_FACTORS)} key factors aligned (need {min_aligned})"
        )

    # Quality filters for 70% regime: calm BTC + volume > avg + not news time
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
            factor_aligned=factor_aligned,
            factor_weights=factor_weights,
            price=price,
            raw={"factors": {f.name: f.details for f in factors}, "missing": missing},
        )

    invalidation = [
        f"Close above structure SL {levels.stop_loss}." if direction == Direction.SHORT
        else f"Close below structure SL {levels.stop_loss}.",
        "HTF (4H/D) flips against the trade.",
        "Volume dries up and price re-enters prior range.",
    ]
    risks = [
        "Crypto volatility / wick stop-outs.",
        "Funding / OI can flip quickly.",
        "Macro/news not fully monitored without a calendar API.",
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
        factor_aligned=factor_aligned,
        factor_weights=factor_weights,
        price=price,
        raw={"factors": {f.name: f.details for f in factors}},
    )


_FACTOR_LABELS = {
    "Trend": "trend",
    "Momentum": "momentum",
    "Volume": "volume",
    "Price Action": "priceAction",
    "Smart Money Concepts": "smc",
    "Futures Metrics": "futures",
    "Fundamental Analysis": "fundamental",
}


def format_report(report: SignalReport) -> str:
    """FutureTradeBot-style signal card (plain text for reliable Telegram delivery)."""
    if report.message == NO_TRADE_MSG or not report.is_actionable():
        lines = [
            f"{report.symbol}",
            f"Verdict: {report.verdict.value}",
            f"Confidence: {report.confidence:.0f}%",
            f"HTF: {report.higher_tf_trend}",
            "",
            NO_TRADE_MSG,
            "",
            "Reasons:",
            *[f"• {r}" for r in report.why_valid[:8]],
            "",
            "Factor scores:",
        ]
        for name, score in report.factor_scores.items():
            label = _FACTOR_LABELS.get(name, name)
            w = int(round(report.factor_weights.get(name, 0) * 100))
            mark = "✓" if report.factor_aligned.get(name) else ""
            lines.append(f"• {label}: {score:.0f}% (w{w}%) {mark}".rstrip())
        return "\n".join(lines)

    lv = report.levels
    assert lv is not None
    side = report.side_label()
    price = report.price if report.price is not None else lv.entry

    lines = [
        side,
        report.symbol,
        f"MEXC · TF 15m · Confidence {report.confidence:.0f}%",
        f"HTF: {report.higher_tf_trend}",
        f"Price: {price}",
        "",
        "Why valid",
        *[f"• {w}" for w in report.why_valid[:8]],
        "",
        "Factor scores",
    ]
    for name, score in report.factor_scores.items():
        label = _FACTOR_LABELS.get(name, name)
        w = int(round(report.factor_weights.get(name, 0) * 100))
        mark = "✓" if report.factor_aligned.get(name) else ""
        lines.append(f"• {label}: {score:.0f}% (w{w}%) {mark}".rstrip())

    lines.extend(
        [
            "",
            f"Entry: {lv.entry}",
            f"SL: {lv.stop_loss}",
            f"TP1: {lv.take_profit_1} (R:R {lv.rr_tp1:.2f})",
            f"TP2: {lv.take_profit_2} (R:R {lv.rr_tp2:.2f})",
            f"TP3: {lv.take_profit_3} (R:R {lv.rr_tp3:.2f})",
            f"Size (1% risk): {lv.position_size}  (risk ${lv.risk_amount})",
            f"Est. hold: {report.estimated_holding_time}",
            "",
            "Invalidation",
            *[f"• {x}" for x in report.invalidation],
            "",
            "Major risks",
            *[f"• {x}" for x in report.major_risks],
            "",
            f"Verdict: {report.verdict.value}",
        ]
    )
    return "\n".join(lines)
