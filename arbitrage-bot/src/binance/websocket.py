from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Awaitable, Callable, List, Optional, Sequence

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

from src.engine.book import OrderBookCache, Quote

logger = logging.getLogger(__name__)

OnQuote = Callable[[Quote], Awaitable[None] | None]


class BinanceRest:
    def __init__(self, base_url: str = "https://api.binance.com") -> None:
        self.base_url = base_url.rstrip("/")

    async def exchange_info_symbols(self) -> List[str]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(f"{self.base_url}/api/v3/exchangeInfo")
            resp.raise_for_status()
            data = resp.json()
        return [
            s["symbol"]
            for s in data.get("symbols", [])
            if s.get("status") == "TRADING" and s.get("isSpotTradingAllowed", True)
        ]

    async def filter_tradable(self, wanted: Sequence[str]) -> List[str]:
        live = set(await self.exchange_info_symbols())
        return [s.upper() for s in wanted if s.upper() in live]


class BinanceBookTickerStream:
    """
    Subscribes to combined bookTicker streams and pushes top-of-book updates.
    Binance allows many streams on one connection; we chunk if needed.
    """

    def __init__(
        self,
        symbols: Sequence[str],
        book: OrderBookCache,
        *,
        ws_base: str = "wss://stream.binance.com:9443",
        on_quote: Optional[OnQuote] = None,
        chunk_size: int = 80,
    ) -> None:
        self.symbols = [s.lower() for s in symbols]
        self.book = book
        self.ws_base = ws_base.rstrip("/")
        self.on_quote = on_quote
        self.chunk_size = chunk_size
        self._tasks: List[asyncio.Task] = []
        self._stop = asyncio.Event()
        self.connected = False
        self.messages = 0
        self.last_message_at = 0.0

    def _urls(self) -> List[str]:
        urls = []
        for i in range(0, len(self.symbols), self.chunk_size):
            chunk = self.symbols[i : i + self.chunk_size]
            streams = "/".join(f"{s}@bookTicker" for s in chunk)
            urls.append(f"{self.ws_base}/stream?streams={streams}")
        return urls

    async def start(self) -> None:
        self._stop.clear()
        for url in self._urls():
            self._tasks.append(asyncio.create_task(self._run_one(url)))

    async def stop(self) -> None:
        self._stop.set()
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self.connected = False

    async def _run_one(self, url: str) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                async with websockets.connect(
                    url, ping_interval=15, ping_timeout=15, max_queue=1024
                ) as ws:
                    self.connected = True
                    backoff = 1.0
                    logger.info("Binance WS connected (%d symbols)", len(self.symbols))
                    async for raw in ws:
                        if self._stop.is_set():
                            break
                        self._handle_message(raw)
            except asyncio.CancelledError:
                raise
            except ConnectionClosed as exc:
                self.connected = False
                logger.warning("WS closed: %s — reconnecting in %.1fs", exc, backoff)
            except Exception as exc:  # noqa: BLE001
                self.connected = False
                logger.warning("WS error: %s — reconnecting in %.1fs", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

    def _handle_message(self, raw: str | bytes) -> None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return
        data = payload.get("data", payload)
        symbol = data.get("s")
        if not symbol:
            return
        try:
            bid = float(data["b"])
            ask = float(data["a"])
            bid_qty = float(data.get("B", 0) or 0)
            ask_qty = float(data.get("A", 0) or 0)
        except (KeyError, TypeError, ValueError):
            return
        quote = Quote(
            symbol=symbol.upper(),
            bid=bid,
            ask=ask,
            bid_qty=bid_qty,
            ask_qty=ask_qty,
            ts_ms=int(time.time() * 1000),
        )
        self.book.update(quote)
        self.messages += 1
        self.last_message_at = time.time()
        if self.on_quote:
            result = self.on_quote(quote)
            if asyncio.iscoroutine(result):
                asyncio.create_task(result)
