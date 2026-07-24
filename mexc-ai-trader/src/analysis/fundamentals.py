"""Fundamental / macro overlays: news, calendar, dominance, DXY proxy, on-chain stubs."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import requests

from src.models import Direction, FactorResult

logger = logging.getLogger(__name__)


# Static high-impact windows can be extended; times are UTC hour ranges as soft blackouts.
# For production, wire a real economic calendar API.
KNOWN_EVENT_HINTS = (
    "FOMC",
    "Federal Reserve",
    "CPI",
    "PPI",
    "NFP",
    "Nonfarm",
    "interest rate",
)


def _coingecko_global() -> dict[str, Any]:
    try:
        resp = requests.get("https://api.coingecko.com/api/v3/global", timeout=15)
        resp.raise_for_status()
        return resp.json().get("data", {})
    except Exception as exc:  # noqa: BLE001
        logger.warning("CoinGecko global failed: %s", exc)
        return {}


def _coingecko_btc_eth() -> dict[str, Any]:
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={
                "ids": "bitcoin,ethereum",
                "vs_currencies": "usd",
                "include_24hr_change": "true",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("CoinGecko price failed: %s", exc)
        return {}


def _news_headlines(api_key: str, query: str = "bitcoin OR ethereum OR crypto OR ETF") -> list[str]:
    if not api_key:
        return []
    try:
        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={"q": query, "language": "en", "sortBy": "publishedAt", "pageSize": 5},
            headers={"X-Api-Key": api_key},
            timeout=15,
        )
        resp.raise_for_status()
        articles = resp.json().get("articles", [])
        return [a.get("title", "") for a in articles if a.get("title")]
    except Exception as exc:  # noqa: BLE001
        logger.warning("NewsAPI failed: %s", exc)
        return []


def news_blackout_active(headlines: list[str], blackout_minutes: int = 60) -> tuple[bool, str]:
    """Heuristic: if major macro keywords appear in recent headlines, advise wait."""
    now = datetime.now(timezone.utc)
    # Without precise calendar timestamps, flag when keywords dominate recent news.
    hits = [h for h in headlines if any(k.lower() in h.lower() for k in KNOWN_EVENT_HINTS)]
    # Also soft blackout around typical US data release hours (12:30–14:30 UTC) on weekdays
    if now.weekday() < 5 and 12 <= now.hour <= 14 and now.minute < blackout_minutes:
        return True, "Soft macro release window (UTC ~12:30–14:30) — wait 30–60m if event due"
    if hits:
        return True, f"Major news keywords in headlines: {hits[0][:80]}"
    return False, "No immediate macro blackout detected"


def analyze_fundamentals(newsapi_key: str = "", symbol: str = "BTC_USDT") -> FactorResult:
    details: list[str] = []
    bull = 0.0
    bear = 0.0

    global_data = _coingecko_global()
    btc_dom = None
    if global_data:
        btc_dom = global_data.get("market_cap_percentage", {}).get("btc")
        mcap_change = global_data.get("market_cap_change_percentage_24h_usd")
        if btc_dom is not None:
            details.append(f"Bitcoin dominance: {btc_dom:.2f}%")
            # Rising dominance often risk-off for alts
            if symbol not in ("BTC_USDT", "BTCUSDT") and btc_dom >= 55:
                bear += 1
                details.append("High BTC.D — caution on alt LONGS")
            elif symbol.startswith("BTC") and btc_dom >= 50:
                bull += 0.5
                details.append("BTC dominance supportive for BTC bias")
        if mcap_change is not None:
            details.append(f"Global mcap 24h change: {mcap_change:.2f}%")
            if mcap_change > 1:
                bull += 1
            elif mcap_change < -1:
                bear += 1

    prices = _coingecko_btc_eth()
    if prices:
        btc_chg = prices.get("bitcoin", {}).get("usd_24h_change")
        eth_chg = prices.get("ethereum", {}).get("usd_24h_change")
        if btc_chg is not None:
            details.append(f"BTC 24h change: {btc_chg:.2f}%")
        if eth_chg is not None:
            details.append(f"ETH 24h change: {eth_chg:.2f}%")

    # ETF flows / DXY / whale / on-chain — require paid APIs; document gracefully
    details.append("ETF inflows/outflows: connect Glassnode/SoSoValue API for live data (stub)")
    details.append("DXY: connect FX/macro feed for live dollar index (stub)")
    details.append("Whale wallets / on-chain: connect Glassnode/CryptoQuant (stub)")
    details.append("Fed/CPI/PPI/NFP: use economic calendar API for precise timestamps")

    headlines = _news_headlines(newsapi_key)
    if headlines:
        details.append("Recent headlines:")
        details.extend([f"  • {h}" for h in headlines[:3]])
        bearish_words = ("hack", "sec charges", "ban", "crash", "lawsuit", "outflow")
        bullish_words = ("etf inflow", "approval", "adoption", "all-time high", "partnership")
        joined = " ".join(headlines).lower()
        if any(w in joined for w in bearish_words):
            bear += 1
            details.append("News tone leans risk-off")
        if any(w in joined for w in bullish_words):
            bull += 1
            details.append("News tone leans risk-on")
    else:
        details.append("News feed inactive (set NEWSAPI_KEY for live headlines)")

    blackout, blackout_msg = news_blackout_active(headlines)
    details.append(blackout_msg)

    if bull > bear:
        direction = Direction.LONG
        score = min(100.0, 50 + bull * 15)
    elif bear > bull:
        direction = Direction.SHORT
        score = min(100.0, 50 + bear * 15)
    else:
        direction = Direction.NONE
        score = 50.0

    if blackout:
        score = min(score, 35.0)
        direction = Direction.NONE
        details.append("Fundamental blackout — NO TRADE until event risk clears")

    return FactorResult(
        name="Fundamental Analysis",
        score=score,
        direction=direction,
        details=details,
        aligned=not blackout and score >= 55,
        weight=0.05,
    )
