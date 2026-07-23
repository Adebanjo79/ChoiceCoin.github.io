"""MEXC Futures public REST client."""

from __future__ import annotations

import logging
import time
from typing import Any

import pandas as pd
import requests

logger = logging.getLogger(__name__)

INTERVAL_MAP = {
    "Min15": "Min15",
    "15m": "Min15",
    "Min60": "Min60",
    "1H": "Min60",
    "1h": "Min60",
    "Hour4": "Hour4",
    "4H": "Hour4",
    "4h": "Hour4",
    "Day1": "Day1",
    "1D": "Day1",
    "D": "Day1",
}


class MexcFuturesClient:
    def __init__(self, base_url: str = "https://contract.mexc.com", timeout: int = 20):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "mexc-ai-trader/1.0"})

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        for attempt in range(3):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                resp.raise_for_status()
                payload = resp.json()
                if isinstance(payload, dict) and payload.get("success") is False:
                    raise RuntimeError(f"MEXC error on {path}: {payload}")
                return payload.get("data", payload) if isinstance(payload, dict) else payload
            except Exception as exc:  # noqa: BLE001
                wait = 1.5 * (attempt + 1)
                logger.warning("MEXC GET %s failed (%s); retry in %.1fs", path, exc, wait)
                time.sleep(wait)
        raise RuntimeError(f"MEXC GET failed after retries: {path}")

    def list_contracts(self) -> list[dict[str, Any]]:
        data = self._get("/api/v1/contract/detail")
        if isinstance(data, list):
            return data
        return data.get("data", data) if isinstance(data, dict) else []

    def list_usdt_perpetuals(self, whitelist: list[str] | None = None) -> list[str]:
        contracts = self.list_contracts()
        symbols: list[str] = []
        for c in contracts:
            symbol = str(c.get("symbol", ""))
            quote = str(c.get("quoteCoin") or c.get("settleCoin") or "")
            state = c.get("state", 0)
            # state 0 = enabled on MEXC
            if state not in (0, "0", None):
                continue
            if not symbol.endswith("_USDT") and quote.upper() not in ("USDT", ""):
                continue
            if symbol.endswith("_USDT"):
                symbols.append(symbol)
        symbols = sorted(set(symbols))
        if whitelist:
            allow = {s.upper() for s in whitelist}
            symbols = [s for s in symbols if s in allow]
        return symbols

    def get_ticker(self, symbol: str | None = None) -> dict[str, Any] | list[dict[str, Any]]:
        params = {"symbol": symbol} if symbol else None
        return self._get("/api/v1/contract/ticker", params=params)

    def get_funding_rate(self, symbol: str) -> dict[str, Any]:
        return self._get(f"/api/v1/contract/funding_rate/{symbol}")

    def get_klines(self, symbol: str, interval: str = "Min15", limit: int = 250) -> pd.DataFrame:
        mexc_interval = INTERVAL_MAP.get(interval, interval)
        # MEXC returns arrays of OHLCV keyed by field
        data = self._get(f"/api/v1/contract/kline/{symbol}", params={"interval": mexc_interval})
        if not data:
            return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])

        if isinstance(data, dict) and "time" in data:
            df = pd.DataFrame(
                {
                    "time": data.get("time", []),
                    "open": data.get("open", []),
                    "high": data.get("high", []),
                    "low": data.get("low", []),
                    "close": data.get("close", []),
                    "volume": data.get("vol", data.get("volume", [])),
                }
            )
        elif isinstance(data, list):
            # fallback list-of-lists / list-of-dicts
            rows = []
            for item in data:
                if isinstance(item, dict):
                    rows.append(
                        {
                            "time": item.get("time") or item.get("t"),
                            "open": item.get("open") or item.get("o"),
                            "high": item.get("high") or item.get("h"),
                            "low": item.get("low") or item.get("l"),
                            "close": item.get("close") or item.get("c"),
                            "volume": item.get("vol") or item.get("volume") or item.get("v"),
                        }
                    )
                elif isinstance(item, (list, tuple)) and len(item) >= 6:
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
            df = pd.DataFrame(rows)
        else:
            return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])

        for col in ("open", "high", "low", "close", "volume"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
        if limit and len(df) > limit:
            df = df.iloc[-limit:].reset_index(drop=True)
        return df

    def get_depth(self, symbol: str, limit: int = 50) -> dict[str, Any]:
        return self._get(f"/api/v1/contract/depth/{symbol}", params={"limit": limit})

    def get_deals(self, symbol: str, limit: int = 100) -> list[dict[str, Any]]:
        data = self._get(f"/api/v1/contract/deals/{symbol}", params={"limit": limit})
        return data if isinstance(data, list) else []
