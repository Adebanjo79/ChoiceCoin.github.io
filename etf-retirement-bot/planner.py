"""Retirement compound-growth planner for monthly ETF investing."""

from __future__ import annotations

from dataclasses import dataclass

from etfs import (
    DEFAULT_EXPECTED_RETURN_PCT,
    DEFAULT_MONTHLY_GBP,
    DEFAULT_YEARS,
    OPTIMISTIC_RETURN_PCT,
)


@dataclass(frozen=True)
class Projection:
    monthly_gbp: float
    years: int
    annual_return_pct: float
    total_contributed: float
    final_value: float
    growth: float


def future_value_monthly(
    monthly_gbp: float,
    years: int,
    annual_return_pct: float,
) -> Projection:
    """Future value of monthly contributions with monthly compounding."""
    if monthly_gbp < 0:
        raise ValueError("monthly_gbp must be >= 0")
    if years < 1:
        raise ValueError("years must be >= 1")
    if annual_return_pct <= -100:
        raise ValueError("annual_return_pct must be > -100")

    months = years * 12
    r = annual_return_pct / 100.0 / 12.0
    contributed = monthly_gbp * months

    if abs(r) < 1e-12:
        final = contributed
    else:
        # FV of ordinary annuity: P * (((1+r)^n - 1) / r)
        final = monthly_gbp * (((1 + r) ** months - 1) / r)

    return Projection(
        monthly_gbp=monthly_gbp,
        years=years,
        annual_return_pct=annual_return_pct,
        total_contributed=round(contributed, 2),
        final_value=round(final, 2),
        growth=round(final - contributed, 2),
    )


def parse_plan_args(args: list[str]) -> tuple[float, int, float | None]:
    """Parse optional args: [monthly] [years] [return%].

    Examples:
      [] -> 100, 30, None
      [150] -> 150, 30, None
      [100, 25] -> 100, 25, None
      [100, 30, 8] -> 100, 30, 8
    """
    monthly = DEFAULT_MONTHLY_GBP
    years = DEFAULT_YEARS
    rate: float | None = None

    if len(args) >= 1:
        monthly = float(args[0])
    if len(args) >= 2:
        years = int(float(args[1]))
    if len(args) >= 3:
        rate = float(args[2])

    if monthly <= 0:
        raise ValueError("Monthly amount must be positive.")
    if years < 1 or years > 60:
        raise ValueError("Years must be between 1 and 60.")
    if rate is not None and (rate <= -100 or rate > 40):
        raise ValueError("Return % must be between -99 and 40.")

    return monthly, years, rate


def format_gbp(amount: float) -> str:
    return f"£{amount:,.0f}" if amount >= 100 else f"£{amount:,.2f}"


def build_plan_summary(
    monthly_gbp: float = DEFAULT_MONTHLY_GBP,
    years: int = DEFAULT_YEARS,
    custom_rate: float | None = None,
) -> str:
    realistic = future_value_monthly(
        monthly_gbp, years, custom_rate or DEFAULT_EXPECTED_RETURN_PCT
    )
    optimistic = future_value_monthly(monthly_gbp, years, OPTIMISTIC_RETURN_PCT)
    cautious = future_value_monthly(monthly_gbp, years, 5.0)

    rate_label = (
        f"{custom_rate:.1f}% (your input)"
        if custom_rate is not None
        else f"~{DEFAULT_EXPECTED_RETURN_PCT:.0f}% (realistic long-run equity planning rate)"
    )

    return (
        f"<b>Monthly retirement projection</b>\n"
        f"Investing {format_gbp(monthly_gbp)}/month for {years} years\n\n"
        f"<b>Realistic scenario</b> — {rate_label}\n"
        f"• Contributed: {format_gbp(realistic.total_contributed)}\n"
        f"• Estimated pot: <b>{format_gbp(realistic.final_value)}</b>\n"
        f"• Growth: {format_gbp(realistic.growth)}\n\n"
        f"<b>Cautious</b> — ~5%/year\n"
        f"• Estimated pot: {format_gbp(cautious.final_value)}\n\n"
        f"<b>Optimistic 15%/year</b> (possible in strong decades, not reliable)\n"
        f"• Estimated pot: {format_gbp(optimistic.final_value)}\n\n"
        "These are math illustrations only — markets do not guarantee any return."
    )


def crash_and_return_reality_check() -> str:
    return (
        "<b>Honest reality check</b>\n\n"
        "<b>Can an ETF do 15% every year?</b>\n"
        "No. Global stock markets have sometimes delivered strong decades "
        "(including stretches near ~15% for US large-caps), but <b>15% every year "
        "is not a dependable long-term plan</b>. A realistic planning range for "
        "a diversified global equity ETF is closer to <b>~7–10% average annual</b> "
        "over very long periods — with many flat or negative years mixed in.\n\n"
        "<b>Can it never crash?</b>\n"
        "No. Even the best diversified equity ETFs can drop <b>30–50%+</b> in a "
        "bad crash (2008, early 2020, etc.). What reduces long-term damage is:\n"
        "• Broad diversification (global index)\n"
        "• Low costs\n"
        "• Investing every month (pound-cost averaging)\n"
        "• Not selling in a panic\n"
        "• A long horizon (15–40 years)\n\n"
        "<b>Best fit for £100/month retirement</b>\n"
        "A low-cost global accumulating ETF such as <b>VWRP</b> inside a UK "
        "Stocks & Shares ISA is the simplest durable approach. It will still "
        "crash sometimes — the plan is to keep buying and hold through it."
    )
