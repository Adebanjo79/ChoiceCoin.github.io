"""Institutional multi-factor scoring engine — MEXC Spot."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from config import Settings
from src.analysis.breakout import analyze_breakout_setup
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
from src.risk import build_moonshot_levels, build_trade_levels

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

# Cryptobull-style: emphasize breakout structure + volume + momentum
BREAKOUT_WEIGHTS = {
    "Breakout Setup": 0.30,
    "Volume": 0.20,
    "Momentum": 0.15,
    "Trend": 0.10,
    "Price Action": 0.10,
    "Smart Money Concepts": 0.05,
    "Spot Metrics": 0.05,
    "Fundamental Analysis": 0.05,
}

BREAKOUT_KEY_FACTORS = ("Breakout Setup", "Volume", "Momentum")


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
        return Verdict.NO_TRADE if confidence < min_confidence else Verdict.WAIT
    if direction == Direction.LONG:
        return Verdict.STRONG_BUY if confidence >= 92 else Verdict.BUY
    return Verdict.STRONG_SELL if confidence >= 92 else Verdict.SELL


def _holding_time(tf_primary: str = "Min15", setup_mode: str = "standard") -> str:
    if setup_mode == "breakout":
        return "2d – 14d (spot breakout swing / Cryptobull-style)"
    return {
        "Min15": "30m – 6h (scalp/intraday spot)",
        "Min60": "2h – 24h (intraday/swing spot)",
        "Hour4": "12h – 5d (swing spot)",
        "Day1": "3d – 3w (position spot)",
    }.get(tf_primary, "2h – 24h spot")


def _pick_level_frame(frames: dict[str, pd.DataFrame], setup_mode: str) -> pd.DataFrame | None:
    if setup_mode == "breakout":
        for key in ("Day1", "Hour4", "Min15", "Min60"):
            df = frames.get(key)
            if df is not None and not getattr(df, "empty", True) and len(df) >= 30:
                return df
    for key in ("Min15", "Min60", "Hour4", "Day1"):
        df = frames.get(key)
        if df is not None and not getattr(df, "empty", True) and len(df) >= 30:
            return df
    return None


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
    setup_mode = getattr(settings, "setup_mode", "standard")
    primary = _pick_level_frame(frames, setup_mode)
    breakout_factor = analyze_breakout_setup(frames) if setup_mode == "breakout" else None

    # ------------------------------------------------------------------
    # AGGRESSIVE BREAKOUT PATH: no institutional hard-blocks
    # Immediate STRONG BUY when confidence >= MIN_CONFIDENCE (default 80).
    # Lower-scoring breakouts keep levels as WAIT candidates for daily top-3.
    # TP ladder: TP1=50%, TP2=200%, TP3=800% (configurable).
    # ------------------------------------------------------------------
    if (
        setup_mode == "breakout"
        and getattr(settings, "breakout_aggressive", True)
        and breakout_factor is not None
        and primary is not None
        and breakout_factor.score >= getattr(settings, "breakout_min_score", 55.0)
    ):
        levels = build_moonshot_levels(
            primary,
            account_balance=settings.account_balance_usdt,
            risk_pct=settings.risk_pct,
            max_stop_pct=settings.effective_max_stop_pct(),
            tp1_pct_pct=settings.tp1_pct,
            tp2_pct_pct=settings.tp2_pct,
            tp3_pct_pct=settings.tp3_pct,
        )
        confidence = round(min(99.0, max(breakout_factor.score, 55.0)), 2)
        why = [
            f"BEST BREAKOUT NOW: {breakout_factor.details[0] if breakout_factor.details else 'spot breakout'}",
            *breakout_factor.details[:5],
            f"TP ladder: +{settings.tp1_pct:.0f}% / +{settings.tp2_pct:.0f}% / +{settings.tp3_pct:.0f}%",
        ]
        if levels is None:
            return SignalReport(
                symbol=symbol,
                direction=Direction.NONE,
                confidence=confidence,
                verdict=Verdict.WAIT,
                message=NO_TRADE_MSG,
                why_valid=["Breakout seen but could not build price levels"],
                higher_tf_trend=higher_tf_summary(frames),
                factor_scores={"Breakout Setup": breakout_factor.score},
                trade_style="SPOT_BREAKOUT",
            )

        min_conf = settings.min_confidence
        force_sb = getattr(settings, "force_strong_buy", True)
        if confidence >= min_conf:
            verdict = Verdict.STRONG_BUY if force_sb or confidence >= 80 else Verdict.BUY
            direction = Direction.LONG
            message = "SPOT BREAKOUT SETUP VALID"
        else:
            # Keep levels so daily quota can promote top picks to STRONG BUY
            verdict = Verdict.WAIT
            direction = Direction.LONG
            message = NO_TRADE_MSG
            why = [
                f"Breakout candidate below {min_conf:.0f}% (score {confidence:.1f}%) — eligible for daily top-3",
                *why,
            ]

        return SignalReport(
            symbol=symbol,
            direction=direction,
            confidence=confidence,
            verdict=verdict,
            message=message,
            why_valid=why,
            higher_tf_trend=higher_tf_summary(frames),
            levels=levels,
            estimated_holding_time="1d – 21d (aggressive spot moonshot ladder)",
            invalidation=[
                f"Close beyond stop-loss at {levels.stop_loss}",
                "Breakout fails and price re-enters prior range",
            ],
            major_risks=[
                "800% targets are rare — scale out at TP1/TP2",
                "High-volatility alts can dump fast — use the stop",
                f"Sized for {settings.account_balance_usdt:.0f} USDT spot account",
            ],
            factor_scores={"Breakout Setup": round(breakout_factor.score, 2)},
            trade_style="SPOT_BREAKOUT",
            raw={"factors": {"Breakout Setup": breakout_factor.details}},
        )

    factors: list[FactorResult] = [
        analyze_trend(frames),
        analyze_momentum(primary, adx_min=settings.adx_min),
        analyze_volume(primary, spike_mult=settings.volume_spike_mult),
        analyze_price_action(primary),
        analyze_smc(primary),
        analyze_spot_metrics(ticker, trades=deals, depth=depth),
        fundamentals_cache or analyze_fundamentals(settings.newsapi_key, symbol=symbol),
    ]
    if breakout_factor is not None:
        factors.insert(0, breakout_factor)

    weights = BREAKOUT_WEIGHTS if setup_mode == "breakout" else WEIGHTS
    key_factors = BREAKOUT_KEY_FACTORS if setup_mode == "breakout" else KEY_FACTORS
    for f in factors:
        f.weight = weights.get(f.name, f.weight)

    direction = _combine_direction(factors)
    # Breakout mode is spot-long biased (2x-style upside hunts)
    if setup_mode == "breakout" and breakout_factor and breakout_factor.aligned:
        direction = Direction.LONG

    confidence = (
        _weighted_confidence(factors, direction)
        if direction != Direction.NONE
        else _weighted_confidence(factors, Direction.LONG)
    )
    if setup_mode == "breakout" and breakout_factor and breakout_factor.aligned:
        confidence = round(min(99.0, max(confidence, breakout_factor.score * 0.85 + confidence * 0.15)), 2)

    aligned_keys = [f.name for f in factors if f.name in key_factors and f.aligned]
    missing = [name for name in key_factors if name not in aligned_keys]
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
    pa = next(f for f in factors if f.name == "Price Action")

    # In breakout mode, require a real breakout pattern (channel/wedge OR resistance)
    if setup_mode != "breakout":
        if "conflicting higher-timeframe" in " ".join(trend.details).lower():
            reject_reasons.append("Conflicting higher-timeframe trends")
    elif breakout_factor and not breakout_factor.aligned:
        # Soft gate: only hard-reject if breakout score is also weak
        if breakout_factor.score < 60:
            reject_reasons.append("No confirmed channel/resistance breakout yet")

    breakout_words = ("Breakout", "Breakdown", "CRYPTOBULL", "trendline", "wedge", "channel", "resistance")
    has_break = any(
        any(w.lower() in d.lower() for w in breakout_words)
        for d in (pa.details + (breakout_factor.details if breakout_factor else []))
    )
    if any("LOW LIQUIDITY" in d for d in spot.details) and not has_break:
        reject_reasons.append("Low liquidity without clear breakout")
    # News blackout still applies, but not soft "wait" wording alone in breakout mode
    if any("blackout" in d.lower() for d in fund.details):
        reject_reasons.append("Major news / macro window within 30–60 minutes")

    min_aligned = getattr(settings, "min_aligned_factors", 2)
    if setup_mode == "breakout":
        min_aligned = 1 if (breakout_factor and breakout_factor.aligned) else min(min_aligned, 2)
    if len(aligned_keys) < min_aligned:
        reject_reasons.append(
            f"Only {len(aligned_keys)}/{len(key_factors)} key factors aligned (need {min_aligned})"
        )

    # Quality filters: in breakout mode, require volume but relax BTC chop gate
    if getattr(settings, "quality_filters", True):
        btc_vol = btc_atr_pct(btc_df)
        if setup_mode == "breakout":
            require_vol = True
            # If breakout detector already saw volume expansion, don't double-punish
            if breakout_factor and any("volume" in d.lower() and ("x1." in d.lower() or "x2." in d.lower() or "Strong volume" in d) for d in breakout_factor.details):
                require_vol = False
            q_rejects = apply_quality_filters(
                primary=primary,
                fund_details=fund.details,
                btc_volatility_pct=btc_vol if btc_vol is not None else 0.0,
                max_btc_volatility_pct=max(settings.max_btc_volatility_pct, 2.5),
                require_volume_above_avg=require_vol,
            )
            q_rejects = [
                r
                for r in q_rejects
                if "BTC volatility unavailable" not in r and "News/macro window" not in r
            ]
        else:
            q_rejects = apply_quality_filters(
                primary=primary,
                fund_details=fund.details,
                btc_volatility_pct=btc_vol,
                max_btc_volatility_pct=settings.max_btc_volatility_pct,
                require_volume_above_avg=settings.require_volume_above_avg,
            )
        reject_reasons.extend(q_rejects)
        if btc_vol is not None:
            why.append(f"BTC ATR%={btc_vol:.2f}")

    if direction == Direction.NONE:
        reject_reasons.append("No clear directional alignment across factors")

    target_upside = settings.effective_target_upside_pct()
    max_stop = settings.effective_max_stop_pct()
    levels = None
    if direction in (Direction.LONG, Direction.SHORT) and primary is not None:
        levels = build_trade_levels(
            primary,
            direction,
            account_balance=settings.account_balance_usdt,
            risk_pct=settings.risk_pct,
            min_rr=settings.min_rr if setup_mode != "breakout" else min(settings.min_rr, 2.0),
            preferred_rr=settings.preferred_rr,
            target_upside_pct=target_upside,
            max_stop_pct=max_stop,
            clamp_stop=(setup_mode == "breakout"),
        )
        if levels is None:
            reject_reasons.append("Risk:Reward < minimum or stop beyond acceptable risk")

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
            trade_style="SPOT_BREAKOUT" if setup_mode == "breakout" else "SPOT",
            raw={"factors": {f.name: f.details for f in factors}, "missing": missing},
        )

    invalidation = [
        f"Close beyond stop-loss at {levels.stop_loss}",
        "Price falls back inside the broken channel/wedge",
        "Volume dries up and breakout fails (fakeout)",
    ]
    risks = [
        "Altcoin breakouts can wick hard both ways — use the stop",
        "2x-style targets are not guaranteed; scale out at TP1/TP2",
        "Unexpected macro headline / BTC dump can invalidate alts",
        f"Account {settings.account_balance_usdt:.0f} USDT | TP3 aim ≈{target_upside:.0f}%",
    ]
    if breakout_factor and breakout_factor.aligned:
        why = [
            f"CRYPTOBULL-STYLE: {next((d for d in breakout_factor.details if 'Structure:' in d), 'channel/wedge breakout')}",
            *why[:6],
        ]

    verdict = _verdict(direction, confidence, min_confidence=settings.min_confidence)
    return SignalReport(
        symbol=symbol,
        direction=direction,
        confidence=confidence,
        verdict=verdict,
        message="SPOT BREAKOUT SETUP VALID" if setup_mode == "breakout" else "SPOT TRADE SETUP VALID",
        why_valid=why or ["Multi-factor confluence ≥ threshold"],
        higher_tf_trend=htf,
        levels=levels,
        estimated_holding_time=_holding_time("Day1", setup_mode=setup_mode),
        invalidation=invalidation,
        major_risks=risks,
        factor_scores=factor_scores,
        trade_style="SPOT_BREAKOUT" if setup_mode == "breakout" else "SPOT",
        raw={"factors": {f.name: f.details for f in factors}},
    )


def format_report(report: SignalReport) -> str:
    shown = display_symbol(report.symbol)
    style = "BREAKOUT SWING" if report.trade_style == "SPOT_BREAKOUT" else "SPOT"
    lines = [
        f"📊 MEXC {style} Signal — {shown}",
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
