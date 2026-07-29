"""Recommendation message builders for the ETF retirement Telegram bot."""

from __future__ import annotations

from html import escape

from etfs import ETF, recommend_for_monthly_retirement
from planner import format_gbp


DISCLAIMER = (
    "<i>Educational only — not personalised financial advice. "
    "Investments can fall as well as rise. Past performance is not a guide "
    "to future results. Consider a regulated adviser if unsure.</i>"
)


def format_etf_card(etf: ETF, rank: int | None = None) -> str:
    prefix = f"{rank}. " if rank is not None else ""
    return (
        f"<b>{prefix}{escape(etf.ticker)}</b> — {escape(etf.name)}\n"
        f"Tracks: {escape(etf.tracks)}\n"
        f"OCF: {etf.ocf_pct:.2f}% · {escape(etf.share_class)} · Risk: {escape(etf.risk)}\n"
        f"Why: {escape(etf.why)}\n"
        f"Best for: {escape(etf.best_for)}\n"
        f"Long-run reference (not a promise): ~{etf.approx_long_run_return_pct:.1f}%/yr avg\n"
        f"Crash note: {escape(etf.crash_resilience)}"
    )


def build_recommendation(
    monthly_gbp: float = 100.0,
    years: int = 30,
    risk: str = "balanced",
) -> str:
    picks = recommend_for_monthly_retirement(monthly_gbp, years, risk)[:4]
    top = picks[0]

    lines = [
        "<b>Best fit for a long-term monthly retirement plan</b>",
        f"Budget: {format_gbp(monthly_gbp)}/month · Horizon: {years} years · Style: {escape(risk)}",
        "",
        "<b>Primary pick</b>",
        format_etf_card(top),
        "",
        "<b>Suggested simple plan</b>",
        f"1. Open a UK Stocks &amp; Shares ISA (tax-free growth).",
        f"2. Set a monthly standing order for {format_gbp(monthly_gbp)}.",
        f"3. Buy <b>{escape(top.ticker)}</b> (accumulating) every month.",
        "4. Ignore short-term noise; review once a year.",
        "",
        "<b>About 15% / year and 'no crash'</b>",
        "No diversified stock ETF can promise 15% annually or zero crashes. "
        f"<b>{escape(top.ticker)}</b> is chosen because it maximises diversification "
        "and keeps costs low — the traits that historically help long retirement plans "
        "survive crashes and compound wealth.",
        "",
        "<b>Other strong options</b>",
    ]
    for i, etf in enumerate(picks[1:], start=2):
        lines.append("")
        lines.append(format_etf_card(etf, rank=i))

    lines.extend(["", DISCLAIMER])
    return "\n".join(lines)


def build_etf_list() -> str:
    from etfs import list_etfs

    lines = ["<b>Curated retirement ETFs (UK / LSE)</b>", ""]
    for i, etf in enumerate(list_etfs(), start=1):
        lines.append(format_etf_card(etf, rank=i))
        lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def build_compare(tickers: list[str]) -> str:
    from etfs import get_etf

    found: list[ETF] = []
    missing: list[str] = []
    for raw in tickers:
        etf = get_etf(raw)
        if etf:
            found.append(etf)
        else:
            missing.append(raw.upper())

    if not found:
        known = ", ".join(sorted({e.ticker for e in __import__("etfs").list_etfs()}))
        return (
            "Could not find those tickers.\n"
            f"Try: /compare VWRP VUAG\nKnown: {known}"
        )

    lines = ["<b>ETF comparison</b>", ""]
    for etf in found:
        lines.append(format_etf_card(etf))
        lines.append("")

    if len(found) >= 2:
        cheapest = min(found, key=lambda e: e.ocf_pct)
        broadest = max(found, key=lambda e: e.suitability_score)
        lines.append(
            f"<b>Quick take:</b> lowest cost is <b>{escape(cheapest.ticker)}</b> "
            f"({cheapest.ocf_pct:.2f}%); strongest overall retirement fit here is "
            f"<b>{escape(broadest.ticker)}</b>."
        )
        lines.append("")

    if missing:
        lines.append("Unknown tickers: " + ", ".join(escape(m) for m in missing))
        lines.append("")

    lines.append(DISCLAIMER)
    return "\n".join(lines)


def build_isa_guide() -> str:
    return (
        "<b>UK Stocks &amp; Shares ISA tip</b>\n\n"
        "For a £100/month retirement plan, an ISA is usually the cleanest wrapper:\n"
        "• Growth and dividends can be tax-free inside the ISA\n"
        "• Annual ISA allowance applies (check current HMRC limit)\n"
        "• Prefer <b>accumulating</b> ETFs (e.g. VWRP) while you are building wealth\n"
        "• Use a low-fee broker; fees matter more than picking the 'perfect' ticker\n\n"
        "Simple default: monthly buy of <b>VWRP</b> inside an ISA, every month, for decades.\n\n"
        + DISCLAIMER
    )


def build_help() -> str:
    return (
        "<b>ETF Retirement Bot</b>\n"
        "Helps you design a simple long-term monthly ETF plan (default £100).\n\n"
        "<b>Commands</b>\n"
        "/recommend [monthly] [years] [risk] — best ETF plan\n"
        "   risk: balanced | growth | calm\n"
        "/plan [monthly] [years] [return%] — compound growth projection\n"
        "/etfs — curated ETF list\n"
        "/compare TICKER [TICKER…] — side-by-side compare\n"
        "/etf TICKER — details for one ETF\n"
        "/reality — truth about 15% returns and crashes\n"
        "/isa — UK ISA notes\n"
        "/help — this message\n\n"
        "<b>Examples</b>\n"
        "/recommend 100 30 balanced\n"
        "/plan 100 30\n"
        "/plan 100 30 8\n"
        "/compare VWRP VUAG SWDA\n\n"
        + DISCLAIMER
    )
