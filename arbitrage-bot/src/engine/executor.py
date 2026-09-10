from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from .arbitrage import Opportunity


@dataclass
class Fill:
    id: str
    opportunity_id: str
    kind: str
    path: List[str]
    notional_usd: float
    gross_edge_bps: float
    net_edge_bps: float
    expected_pnl_usd: float
    ts: float
    mode: str
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Portfolio:
    starting_capital_usd: float
    cash_usd: float
    realized_pnl_usd: float = 0.0
    trades: List[Fill] = field(default_factory=list)
    opportunities_seen: int = 0
    last_opportunity: Optional[dict] = None

    def to_dict(self) -> dict:
        equity = self.cash_usd
        return {
            "starting_capital_usd": round(self.starting_capital_usd, 4),
            "cash_usd": round(self.cash_usd, 4),
            "equity_usd": round(equity, 4),
            "realized_pnl_usd": round(self.realized_pnl_usd, 4),
            "return_pct": round(
                ((equity / self.starting_capital_usd) - 1.0) * 100.0, 4
            )
            if self.starting_capital_usd
            else 0.0,
            "trade_count": len(self.trades),
            "opportunities_seen": self.opportunities_seen,
            "last_opportunity": self.last_opportunity,
            "recent_trades": [t.to_dict() for t in self.trades[-25:][::-1]],
        }


class PaperExecutor:
    """
    Simulates fills at the quoted edge.

    This is intentionally conservative: it only books the *net* edge after fees
    and refuses trades larger than available cash / max position.
    """

    def __init__(
        self,
        *,
        starting_capital_usd: float = 68.0,
        max_position_usd: float = 25.0,
        paper_trading: bool = True,
    ) -> None:
        self.paper_trading = paper_trading
        self.max_position_usd = max_position_usd
        self.portfolio = Portfolio(
            starting_capital_usd=starting_capital_usd,
            cash_usd=starting_capital_usd,
        )
        self._cooldown_until: Dict[str, float] = {}
        self.cooldown_seconds = 5.0

    def note_opportunities(self, opps: List[Opportunity]) -> None:
        self.portfolio.opportunities_seen += len(opps)
        if opps:
            self.portfolio.last_opportunity = opps[0].to_dict()

    def maybe_execute(self, opp: Opportunity) -> Optional[Fill]:
        key = "|".join(opp.path)
        now = time.time()
        if self._cooldown_until.get(key, 0) > now:
            return None

        notional = min(opp.notional_usd, self.max_position_usd, self.portfolio.cash_usd)
        if notional < 1.0:
            return None
        if opp.net_edge_bps <= 0:
            return None

        expected_pnl = notional * (opp.net_edge_bps / 10_000.0)

        if not self.paper_trading:
            # Live trading requires signed REST orders + careful partial-fill
            # handling. Keep this path disabled until keys + order router exist.
            raise RuntimeError(
                "Live trading is disabled in this build. Set PAPER_TRADING=true "
                "or extend src/engine/executor.py with signed Binance orders."
            )

        fill = Fill(
            id=str(uuid.uuid4())[:8],
            opportunity_id=key,
            kind=opp.kind,
            path=list(opp.path),
            notional_usd=round(notional, 4),
            gross_edge_bps=opp.gross_edge_bps,
            net_edge_bps=opp.net_edge_bps,
            expected_pnl_usd=round(expected_pnl, 6),
            ts=now,
            mode="paper",
            detail=opp.detail,
        )
        self.portfolio.cash_usd += expected_pnl
        self.portfolio.realized_pnl_usd += expected_pnl
        self.portfolio.trades.append(fill)
        self._cooldown_until[key] = now + self.cooldown_seconds
        return fill
