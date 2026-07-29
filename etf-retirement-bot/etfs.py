"""Curated long-term retirement ETF catalogue (UK / LSE-focused).

Educational data only — not personalised financial advice.
Historical returns are approximate long-run references, not forecasts.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ETF:
    ticker: str
    name: str
    tracks: str
    ocf_pct: float
    region: str
    risk: str  # low / medium / high (relative among these options)
    share_class: str  # Acc or Dist
    why: str
    best_for: str
    approx_long_run_return_pct: float  # rough historical-style reference
    crash_resilience: str
    suitability_score: int  # 1–100 for ranking monthly retirement plans


# Approximate long-run equity references (nominal, not guaranteed):
# Global developed equities historically ~7–10% real / ~8–12% nominal depending on era.
# No ETF is crash-proof; diversification shortens recovery odds over decades.
ETFS: dict[str, ETF] = {
    "VWRP": ETF(
        ticker="VWRP",
        name="Vanguard FTSE All-World UCITS ETF",
        tracks="~3,700 stocks across ~50 countries (developed + emerging)",
        ocf_pct=0.22,
        region="Global",
        risk="medium",
        share_class="Acc",
        why=(
            "One-fund global portfolio: maximum diversification in a single "
            "low-cost accumulating ETF — ideal for hands-off monthly investing."
        ),
        best_for="Default core holding for a £100/month retirement plan",
        approx_long_run_return_pct=8.5,
        crash_resilience=(
            "Can fall 30–50% in a bad crash (like all equities). Broad global "
            "spread historically recovers over multi-year horizons if you keep investing."
        ),
        suitability_score=98,
    ),
    "VWRL": ETF(
        ticker="VWRL",
        name="Vanguard FTSE All-World UCITS ETF (Distributing)",
        tracks="Same as VWRP but pays dividends out as cash",
        ocf_pct=0.22,
        region="Global",
        risk="medium",
        share_class="Dist",
        why="Same global exposure as VWRP; use only if you want dividends paid out.",
        best_for="Income near retirement — prefer VWRP while accumulating",
        approx_long_run_return_pct=8.5,
        crash_resilience="Same market risk as VWRP; compounding is weaker if dividends are spent.",
        suitability_score=82,
    ),
    "SWDA": ETF(
        ticker="SWDA",
        name="iShares Core MSCI World UCITS ETF",
        tracks="~1,400 large/mid developed-market stocks (no emerging markets)",
        ocf_pct=0.20,
        region="Developed world",
        risk="medium",
        share_class="Acc",
        why="Slightly cheaper global developed-markets core; skips emerging markets.",
        best_for="Core holding if you prefer developed markets only",
        approx_long_run_return_pct=8.5,
        crash_resilience="Still equity risk; historically resilient over 15–30+ year horizons.",
        suitability_score=92,
    ),
    "VUAG": ETF(
        ticker="VUAG",
        name="Vanguard S&P 500 UCITS ETF",
        tracks="500 largest US companies",
        ocf_pct=0.07,
        region="USA",
        risk="medium-high",
        share_class="Acc",
        why="Lowest-cost US large-cap exposure; strong historical growth, concentrated in one country.",
        best_for="Satellite / growth tilt — not a sole retirement fund for most people",
        approx_long_run_return_pct=10.0,
        crash_resilience=(
            "US markets have crashed hard (2000, 2008, 2020) and recovered, but "
            "country concentration is riskier than All-World for decades-long plans."
        ),
        suitability_score=78,
    ),
    "SSAC": ETF(
        ticker="SSAC",
        name="iShares MSCI ACWI UCITS ETF",
        tracks="All-country world index (developed + emerging)",
        ocf_pct=0.20,
        region="Global",
        risk="medium",
        share_class="Acc",
        why="Another solid global one-fund option similar in spirit to VWRP.",
        best_for="Alternative to VWRP if your broker prices it better",
        approx_long_run_return_pct=8.5,
        crash_resilience="Diversified equity risk; not crash-proof.",
        suitability_score=90,
    ),
    "VFEM": ETF(
        ticker="VFEM",
        name="Vanguard FTSE Emerging Markets UCITS ETF",
        tracks="Emerging market equities",
        ocf_pct=0.22,
        region="Emerging markets",
        risk="high",
        share_class="Dist",
        why="Higher expected volatility; useful only as a small satellite, not a core.",
        best_for="Optional 5–15% tilt — not a primary retirement ETF",
        approx_long_run_return_pct=7.5,
        crash_resilience="Can crash harder and stay down longer than developed markets.",
        suitability_score=45,
    ),
    "VAGP": ETF(
        ticker="VAGP",
        name="Vanguard Global Aggregate Bond UCITS ETF",
        tracks="Global investment-grade bonds",
        ocf_pct=0.10,
        region="Global bonds",
        risk="low",
        share_class="Acc",
        why="Dampens equity crashes; lowers long-term expected return vs all-stock.",
        best_for="Add when nearer retirement or if you need a calmer ride",
        approx_long_run_return_pct=3.5,
        crash_resilience="Bonds can fall too, but usually less than stocks in equity crashes.",
        suitability_score=70,
    ),
}


DEFAULT_MONTHLY_GBP = 100.0
DEFAULT_YEARS = 30
# Realistic long-run planning default (not a promise of 15%).
DEFAULT_EXPECTED_RETURN_PCT = 8.0
# Aggressive scenario the user asked about — shown as optimistic, not baseline.
OPTIMISTIC_RETURN_PCT = 15.0


def list_etfs() -> list[ETF]:
    return sorted(ETFS.values(), key=lambda e: e.suitability_score, reverse=True)


def get_etf(ticker: str) -> ETF | None:
    return ETFS.get(ticker.strip().upper())


def recommend_for_monthly_retirement(
    monthly_gbp: float = DEFAULT_MONTHLY_GBP,
    years: int = DEFAULT_YEARS,
    risk_preference: str = "balanced",
) -> list[ETF]:
    """Return ranked ETF picks for a simple long-term monthly plan."""
    risk_preference = risk_preference.lower().strip()
    picks = list_etfs()

    if risk_preference in {"calm", "conservative", "low"}:
        # Prefer global equity + note bonds; still keep a growth core.
        preferred = ["VWRP", "SWDA", "VAGP", "SSAC"]
    elif risk_preference in {"growth", "aggressive", "high"}:
        preferred = ["VWRP", "VUAG", "SWDA", "SSAC"]
    else:
        # Balanced default: one global fund first.
        preferred = ["VWRP", "SWDA", "SSAC", "VUAG"]

    ordered: list[ETF] = []
    for ticker in preferred:
        etf = ETFS[ticker]
        if etf not in ordered:
            ordered.append(etf)
    for etf in picks:
        if etf not in ordered:
            ordered.append(etf)

    # Filter out pure satellites for the primary recommendation list.
    if monthly_gbp < 200:
        ordered = [e for e in ordered if e.ticker != "VFEM"]

    _ = years  # reserved for future age/glide-path logic
    return ordered
