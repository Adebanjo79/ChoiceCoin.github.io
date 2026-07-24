"""MEXC Spot public REST client with rate-limit protection."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# Internal TF names → MEXC Spot interval strings
INTERVAL_MAP = {
    "Min15": "15m",
    "15m": "15m",
    "Min60": "60m",
    "1H": "60m",
    "1h": "60m",
    "Hour4": "4h",
    "4H": "4h",
    "4h": "4h",
    "Day1": "1d",
    "1D": "1d",
    "D": "1d",
}


def normalize_spot_symbol(symbol: str) -> str:
    """Accept BTC_USDT / BTC-USDT / btcusdt → BTCUSDT."""
    s = symbol.strip().upper().replace("-", "").replace("_", "").replace("/", "")
    return s


def display_symbol(symbol: str) -> str:
    s = normalize_spot_symbol(symbol)
    if s.endswith("USDT") and len(s) > 4:
        return f"{s[:-4]}/USDT"
    return s


class MexcSpotClient:
    """Shared, thread-safe MEXC Spot client. Throttled to avoid rate limits."""

    def __init__(
        self,
        base_url: str = "https://api.mexc.com",
        timeout: int = 20,
        min_request_interval: float = 0.22,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.min_request_interval = max(0.05, float(min_request_interval))
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "mexc-ai-trader-spot/1.0"})
        self._lock = threading.Lock()
        self._last_request_at = 0.0

    def _throttle(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait = self.min_request_interval - (now - self._last_request_at)
            if wait > 0:
                time.sleep(wait)
            self._last_request_at = time.monotonic()

    @staticmethod
    def _is_rate_limited(exc: Exception) -> bool:
        text = str(exc)
        return "429" in text or "too frequent" in text.lower() or "rate" in text.lower()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        for attempt in range(5):
            self._throttle()
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    raise RuntimeError(f"HTTP 429 on {path}")
                resp.raise_for_status()
                payload = resp.json()
                if isinstance(payload, dict) and payload.get("code") not in (None, 0, 200):
                    # Spot often returns data directly; some errors use code/msg
                    if "msg" in payload and "symbol" not in payload:
                        raise RuntimeError(f"MEXC spot error on {path}: {payload}")
                return payload
            except Exception as exc:  # noqa: BLE001
                if self._is_rate_limited(exc):
                    wait = min(60.0, 5.0 * (2**attempt))
                    logger.warning(
                        "MEXC rate limited on %s — cooling down %.0fs (attempt %d/5)",
                        path,
                        wait,
                        attempt + 1,
                    )
                    time.sleep(wait)
                else:
                    wait = 1.5 * (attempt + 1)
                    logger.warning("MEXC GET %s failed (%s); retry in %.1fs", path, exc, wait)
                    time.sleep(wait)
        raise RuntimeError(f"MEXC GET failed after retries: {path}")

    def list_usdt_spot_pairs(self, whitelist: list[str] | None = None) -> list[str]:
        data = self._get("/api/v3/exchangeInfo")
        symbols: list[str] = []
        for c in data.get("symbols", []) if isinstance(data, dict) else []:
            symbol = str(c.get("symbol", ""))
            quote = str(c.get("quoteAsset") or "")
            status = str(c.get("status", ""))
            spot_ok = c.get("isSpotTradingAllowed", True)
            if quote.upper() != "USDT":
                continue
            if status not in ("1", "ENABLED", "TRADING", ""):
                continue
            if spot_ok is False:
                continue
            if symbol.endswith("USDT"):
                symbols.append(symbol)
        symbols = sorted(set(symbols))
        if whitelist:
            allow = {normalize_spot_symbol(s) for s in whitelist}
            symbols = [s for s in symbols if s in allow]
        return symbols

    def get_ticker_24h(self, symbol: str | None = None) -> dict[str, Any] | list[dict[str, Any]]:
        params = {"symbol": normalize_spot_symbol(symbol)} if symbol else None
        return self._get("/api/v3/ticker/24hr", params=params)

    def get_book_ticker(self, symbol: str) -> dict[str, Any]:
        return self._get("/api/v3/ticker/bookTicker", params={"symbol": normalize_spot_symbol(symbol)})

    def get_klines(self, symbol: str, interval: str = "Min15", limit: int = 250) -> pd.DataFrame:
        mexc_interval = INTERVAL_MAP.get(interval, interval)
        data = self._get(
            "/api/v3/klines",
            params={
                "symbol": normalize_spot_symbol(symbol),
                "interval": mexc_interval,
                "limit": min(int(limit), 1000),
            },
        )
        if not data or not isinstance(data, list):
            return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])

        rows = []
        for item in data:
            if isinstance(item, (list, tuple)) and len(item) >= 6:
                rows.append(
                    {
                        "time": item[0],
                        "open": item[1],
                        "high": item[2],
                        "low": item[3],
                        "close": item[4],
                        "volume": item[5],
                    }
                )
            elif isinstance(item, dict):
                rows.append(
                    {
                        "time": item.get("time") or item.get("t") or item.get("openTime"),
                        "open": item.get("open") or item.get("o"),
                        "high": item.get("high") or item.get("h"),
                        "low": item.get("low") or item.get("l"),
                        "close": item.get("close") or item.get("c"),
                        "volume": item.get("volume") or item.get("v"),
                    }
                )
        df = pd.DataFrame(rows)
        if df.empty:
            return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
        if limit and len(df) > limit:
            df = df.iloc[-limit:].reset_index(drop=True)
        return df

    def get_depth(self, symbol: str, limit: int = 50) -> dict[str, Any]:
        return self._get(
            "/api/v3/depth",
            params={"symbol": normalize_spot_symbol(symbol), "limit": limit},
        )

    def get_trades(self, symbol: str, limit: int = 100) -> list[dict[str, Any]]:
        data = self._get(
            "/api/v3/trades",
            params={"symbol": normalize_spot_symbol(symbol), "limit": limit},
        )
        return data if isinstance(data, list) else []


# Backward-compatible alias used by older imports/tests
MexcFuturesClient = MexcSpotClient
