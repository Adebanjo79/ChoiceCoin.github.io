from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional, Tuple


@dataclass
class Quote:
    symbol: str
    bid: float
    ask: float
    bid_qty: float = 0.0
    ask_qty: float = 0.0
    ts_ms: int = 0

    @property
    def mid(self) -> float:
        if self.bid <= 0 or self.ask <= 0:
            return 0.0
        return (self.bid + self.ask) / 2.0

    @property
    def spread_bps(self) -> float:
        mid = self.mid
        if mid <= 0:
            return 0.0
        return ((self.ask - self.bid) / mid) * 10_000


class OrderBookCache:
    """In-memory top-of-book cache keyed by symbol."""

    def __init__(self) -> None:
        self._quotes: Dict[str, Quote] = {}
        self._updated_at: float = 0.0

    def update(self, quote: Quote) -> None:
        self._quotes[quote.symbol] = quote
        self._updated_at = time.time()

    def get(self, symbol: str) -> Optional[Quote]:
        return self._quotes.get(symbol.upper())

    def all(self) -> Dict[str, Quote]:
        return dict(self._quotes)

    def snapshot(self) -> Dict[str, dict]:
        return {
            sym: {
                "symbol": q.symbol,
                "bid": q.bid,
                "ask": q.ask,
                "bid_qty": q.bid_qty,
                "ask_qty": q.ask_qty,
                "mid": q.mid,
                "spread_bps": round(q.spread_bps, 2),
                "ts_ms": q.ts_ms,
            }
            for sym, q in sorted(self._quotes.items())
        }

    @property
    def size(self) -> int:
        return len(self._quotes)

    @property
    def age_seconds(self) -> float:
        if not self._updated_at:
            return float("inf")
        return time.time() - self._updated_at

    def pairs(self) -> Iterable[Tuple[str, Quote]]:
        return self._quotes.items()
