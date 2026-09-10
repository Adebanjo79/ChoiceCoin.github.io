from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import Settings, get_settings
from src.binance.websocket import BinanceBookTickerStream, BinanceRest
from src.engine.arbitrage import ArbitrageEngine, Opportunity
from src.engine.book import OrderBookCache
from src.engine.executor import PaperExecutor

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent.parent / "dashboard" / "static"


class BotRuntime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.book = OrderBookCache()
        self.engine = ArbitrageEngine(
            self.book,
            taker_fee_bps=settings.taker_fee_bps,
            min_edge_bps=settings.min_edge_bps,
            max_position_usd=settings.max_position_usd,
        )
        self.executor = PaperExecutor(
            starting_capital_usd=settings.starting_capital_usd,
            max_position_usd=settings.max_position_usd,
            paper_trading=settings.paper_trading,
        )
        self.stream: Optional[BinanceBookTickerStream] = None
        self.symbols: List[str] = []
        self.triangle_count = 0
        self.latest_opps: List[Opportunity] = []
        self.started_at = time.time()
        self._scan_task: Optional[asyncio.Task] = None
        self._clients: List[WebSocket] = []
        self._lock = asyncio.Lock()
        self.scans = 0
        self.status = "starting"

    async def start(self) -> None:
        rest = BinanceRest(self.settings.binance_rest_base)
        try:
            self.symbols = await rest.filter_tradable(self.settings.symbols)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to load exchangeInfo: %s — using configured list", exc)
            self.symbols = list(self.settings.symbols)

        self.triangle_count = self.engine.build_triangles(self.symbols)
        self.stream = BinanceBookTickerStream(
            self.symbols,
            self.book,
            ws_base=self.settings.binance_ws_base,
        )
        await self.stream.start()
        self._scan_task = asyncio.create_task(self._scan_loop())
        self.status = "running"
        logger.info(
            "Bot running — %d symbols, %d triangles, paper=%s",
            len(self.symbols),
            self.triangle_count,
            self.settings.paper_trading,
        )

    async def stop(self) -> None:
        self.status = "stopping"
        if self._scan_task:
            self._scan_task.cancel()
            await asyncio.gather(self._scan_task, return_exceptions=True)
        if self.stream:
            await self.stream.stop()
        self.status = "stopped"

    async def _scan_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(0.25)
                if self.book.size < 3:
                    continue
                opps = self.engine.scan(include_near_misses=True)
                self.scans += 1
                self.latest_opps = opps[:20]
                tradeable = self.engine.executable(opps)
                self.executor.note_opportunities(tradeable)
                fills = []
                for opp in tradeable[:3]:
                    fill = self.executor.maybe_execute(opp)
                    if fill:
                        fills.append(fill)
                        logger.info(
                            "PAPER FILL %s edge=%.2fbps pnl=$%.4f",
                            fill.kind,
                            fill.net_edge_bps,
                            fill.expected_pnl_usd,
                        )
                await self._broadcast(self.snapshot(fills=fills))
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("scan loop error")
                await asyncio.sleep(1.0)

    def snapshot(self, fills: Optional[list] = None) -> Dict[str, Any]:
        stream = self.stream
        return {
            "type": "snapshot",
            "status": self.status,
            "paper_trading": self.settings.paper_trading,
            "uptime_sec": round(time.time() - self.started_at, 1),
            "markets": self.book.size,
            "configured_symbols": len(self.symbols),
            "triangles": self.triangle_count,
            "scans": self.scans,
            "ws_connected": bool(stream and stream.connected),
            "ws_messages": stream.messages if stream else 0,
            "book_age_sec": round(self.book.age_seconds, 3)
            if self.book.size
            else None,
            "btc": self._btc_card(),
            "portfolio": self.executor.portfolio.to_dict(),
            "opportunities": [o.to_dict() for o in self.latest_opps],
            "markets_snapshot": self.book.snapshot(),
            "fills": [f.to_dict() for f in (fills or [])],
            "disclaimer": (
                "Paper trading by default. Live arb edges after fees are rare. "
                "Viral $68→$750K stories are not a realistic baseline."
            ),
        }

    def _btc_card(self) -> Optional[dict]:
        q = self.book.get("BTCUSDT")
        if not q:
            return None
        return {
            "symbol": "BTCUSDT",
            "bid": q.bid,
            "ask": q.ask,
            "mid": q.mid,
            "spread_bps": round(q.spread_bps, 3),
        }

    async def register(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.append(ws)
        await ws.send_json(self.snapshot())

    async def unregister(self, ws: WebSocket) -> None:
        async with self._lock:
            if ws in self._clients:
                self._clients.remove(ws)

    async def _broadcast(self, payload: dict) -> None:
        async with self._lock:
            clients = list(self._clients)
        dead = []
        for ws in clients:
            try:
                await ws.send_json(payload)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            await self.unregister(ws)


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or get_settings()
    runtime = BotRuntime(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.basicConfig(
            level=getattr(logging, settings.log_level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        await runtime.start()
        app.state.runtime = runtime
        yield
        await runtime.stop()

    app = FastAPI(title="Binance Arbitrage Bot", lifespan=lifespan)

    @app.get("/api/health")
    async def health() -> dict:
        return {
            "ok": True,
            "status": runtime.status,
            "markets": runtime.book.size,
            "paper_trading": settings.paper_trading,
        }

    @app.get("/api/snapshot")
    async def snapshot() -> dict:
        return runtime.snapshot()

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await runtime.register(ws)
        try:
            while True:
                # Keep alive; client may send pings.
                await ws.receive_text()
        except WebSocketDisconnect:
            await runtime.unregister(ws)
        except Exception:  # noqa: BLE001
            await runtime.unregister(ws)

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
