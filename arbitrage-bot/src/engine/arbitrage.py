from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import List, Optional, Sequence, Tuple

from .book import OrderBookCache, Quote


QUOTE_ASSETS = ("USDT", "BTC", "ETH", "BNB", "USDC", "FDUSD")


def split_symbol(symbol: str) -> Optional[Tuple[str, str]]:
    """Split BINANCE symbols like ETHBTC into (base, quote)."""
    symbol = symbol.upper()
    for quote in sorted(QUOTE_ASSETS, key=len, reverse=True):
        if symbol.endswith(quote) and len(symbol) > len(quote):
            return symbol[: -len(quote)], quote
    return None


@dataclass
class Opportunity:
    kind: str
    path: List[str]
    legs: List[dict]
    gross_edge_bps: float
    net_edge_bps: float
    notional_usd: float
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


class ArbitrageEngine:
    """
    Detects triangular arbitrage and cross-pair dislocations on a single venue.

    Reality check: after fees, true risk-free arb on Binance spot is rare.
    This engine surfaces gross+net edge so you can see how often net > 0.
    """

    def __init__(
        self,
        book: OrderBookCache,
        *,
        taker_fee_bps: float = 10.0,
        min_edge_bps: float = 8.0,
        max_position_usd: float = 25.0,
    ) -> None:
        self.book = book
        self.taker_fee_bps = taker_fee_bps
        self.min_edge_bps = min_edge_bps
        self.max_position_usd = max_position_usd
        self._triangles: List[Tuple[str, str, str, str, str, str]] = []

    def build_triangles(self, symbols: Sequence[str]) -> int:
        """
        Build triangles of the form:
          USDT -> BASE_A -> BASE_B -> USDT
        using pairs like AUSDT, AB, BUSDT (and reverse directions).
        """
        available = {s.upper() for s in symbols}
        bases = set()
        for sym in available:
            parts = split_symbol(sym)
            if parts and parts[1] == "USDT":
                bases.add(parts[0])

        triangles: List[Tuple[str, str, str, str, str, str]] = []
        base_list = sorted(bases)
        for i, a in enumerate(base_list):
            for b in base_list[i + 1 :]:
                a_usdt = f"{a}USDT"
                b_usdt = f"{b}USDT"
                ab = f"{a}{b}"
                ba = f"{b}{a}"
                if a_usdt in available and b_usdt in available:
                    if ab in available:
                        # USDT -> A -> B -> USDT  and reverse
                        triangles.append((a_usdt, ab, b_usdt, a, b, "AB"))
                    if ba in available:
                        triangles.append((a_usdt, ba, b_usdt, a, b, "BA"))

        self._triangles = triangles
        return len(triangles)

    def scan(self, *, include_near_misses: bool = True) -> List[Opportunity]:
        opps: List[Opportunity] = []
        opps.extend(self._scan_triangles(include_near_misses=include_near_misses))
        opps.extend(
            self._scan_btc_eth_consistency(include_near_misses=include_near_misses)
        )
        opps.sort(key=lambda o: o.net_edge_bps, reverse=True)
        # De-dupe by path, keep best
        seen = set()
        unique: List[Opportunity] = []
        for opp in opps:
            key = tuple(opp.path)
            if key in seen:
                continue
            seen.add(key)
            unique.append(opp)
        return unique

    def executable(self, opps: List[Opportunity]) -> List[Opportunity]:
        return [o for o in opps if o.net_edge_bps >= self.min_edge_bps]

    def _scan_triangles(self, *, include_near_misses: bool = True) -> List[Opportunity]:
        results: List[Opportunity] = []
        fee_mult = 1.0 - (self.taker_fee_bps / 10_000.0)

        for a_usdt, cross, b_usdt, a, b, cross_kind in self._triangles:
            qa = self.book.get(a_usdt)
            qb = self.book.get(b_usdt)
            qx = self.book.get(cross)
            if not qa or not qb or not qx:
                continue
            if min(qa.ask, qb.ask, qx.ask, qa.bid, qb.bid, qx.bid) <= 0:
                continue

            # Direction 1: USDT -> buy A -> swap to B -> sell B for USDT
            start = 1.0
            amt_a = (start / qa.ask) * fee_mult
            if cross_kind == "AB":
                amt_b = amt_a * qx.bid * fee_mult
            else:
                amt_b = (amt_a / qx.ask) * fee_mult
            end = amt_b * qb.bid * fee_mult
            gross_end = self._triangle_gross(qa, qb, qx, cross_kind, forward=True)
            net_bps = (end / start - 1.0) * 10_000
            gross_bps = (gross_end - 1.0) * 10_000

            if net_bps >= self.min_edge_bps or (
                include_near_misses and net_bps > -50
            ):
                notional = min(self.max_position_usd, self._cap_notional(qa, qb, qx))
                results.append(
                    Opportunity(
                        kind="triangular",
                        path=[f"USDT->{a}", f"{a}->{b}", f"{b}->USDT"],
                        legs=[
                            {"symbol": a_usdt, "side": "BUY", "price": qa.ask},
                            {
                                "symbol": cross,
                                "side": "SELL" if cross_kind == "AB" else "BUY",
                                "price": qx.bid if cross_kind == "AB" else qx.ask,
                            },
                            {"symbol": b_usdt, "side": "SELL", "price": qb.bid},
                        ],
                        gross_edge_bps=round(gross_bps, 2),
                        net_edge_bps=round(net_bps, 2),
                        notional_usd=round(notional, 2),
                        detail=f"Triangle {a}/{b} forward",
                    )
                )

            # Direction 2: USDT -> buy B -> swap to A -> sell A
            start = 1.0
            amt_b = (start / qb.ask) * fee_mult
            if cross_kind == "AB":
                amt_a = (amt_b / qx.ask) * fee_mult
            else:
                amt_a = amt_b * qx.bid * fee_mult
            end = amt_a * qa.bid * fee_mult
            gross_end = self._triangle_gross(qa, qb, qx, cross_kind, forward=False)
            net_bps = (end / start - 1.0) * 10_000
            gross_bps = (gross_end - 1.0) * 10_000

            if net_bps >= self.min_edge_bps or (
                include_near_misses and net_bps > -50
            ):
                notional = min(self.max_position_usd, self._cap_notional(qa, qb, qx))
                results.append(
                    Opportunity(
                        kind="triangular",
                        path=[f"USDT->{b}", f"{b}->{a}", f"{a}->USDT"],
                        legs=[
                            {"symbol": b_usdt, "side": "BUY", "price": qb.ask},
                            {
                                "symbol": cross,
                                "side": "BUY" if cross_kind == "AB" else "SELL",
                                "price": qx.ask if cross_kind == "AB" else qx.bid,
                            },
                            {"symbol": a_usdt, "side": "SELL", "price": qa.bid},
                        ],
                        gross_edge_bps=round(gross_bps, 2),
                        net_edge_bps=round(net_bps, 2),
                        notional_usd=round(notional, 2),
                        detail=f"Triangle {a}/{b} reverse",
                    )
                )

        return results

    def _triangle_gross(
        self, qa: Quote, qb: Quote, qx: Quote, cross_kind: str, *, forward: bool
    ) -> float:
        if forward:
            amt_a = 1.0 / qa.ask
            amt_b = amt_a * qx.bid if cross_kind == "AB" else amt_a / qx.ask
            return amt_b * qb.bid
        amt_b = 1.0 / qb.ask
        amt_a = amt_b / qx.ask if cross_kind == "AB" else amt_b * qx.bid
        return amt_a * qa.bid

    def _cap_notional(self, qa: Quote, qb: Quote, qx: Quote) -> float:
        # Rough liquidity cap from top-of-book sizes converted to USDT.
        caps = []
        if qa.ask_qty > 0:
            caps.append(qa.ask_qty * qa.ask)
        if qb.bid_qty > 0:
            caps.append(qb.bid_qty * qb.bid)
        if qx.bid_qty > 0 and qa.bid > 0:
            # cross qty * approximate USDT via A or B mid
            caps.append(qx.bid_qty * qa.mid)
        return min(caps) if caps else self.max_position_usd

    def _scan_btc_eth_consistency(
        self, *, include_near_misses: bool = True
    ) -> List[Opportunity]:
        """
        Flag when BTC-quoted and USDT-quoted prices disagree beyond fees.
        Example: ETHBTC * BTCUSDT should ≈ ETHUSDT.
        """
        results: List[Opportunity] = []
        fee_bps = self.taker_fee_bps * 2  # two-leg synthetic vs direct
        btc = self.book.get("BTCUSDT")
        if not btc or btc.mid <= 0:
            return results

        for sym, quote in self.book.pairs():
            parts = split_symbol(sym)
            if not parts or parts[1] != "BTC":
                continue
            base = parts[0]
            usdt_sym = f"{base}USDT"
            usdt_q = self.book.get(usdt_sym)
            if not usdt_q or usdt_q.mid <= 0 or quote.mid <= 0:
                continue

            synth_bid = quote.bid * btc.bid
            synth_ask = quote.ask * btc.ask
            direct_bid = usdt_q.bid
            direct_ask = usdt_q.ask

            def maybe_add(
                gross_bps: float,
                path: List[str],
                legs: List[dict],
                detail: str,
                notional: float,
            ) -> None:
                net_bps = gross_bps - fee_bps
                if net_bps >= self.min_edge_bps or (
                    include_near_misses and net_bps > -40
                ):
                    results.append(
                        Opportunity(
                            kind="synthetic_vs_direct",
                            path=path,
                            legs=legs,
                            gross_edge_bps=round(gross_bps, 2),
                            net_edge_bps=round(net_bps, 2),
                            notional_usd=round(min(self.max_position_usd, notional), 2),
                            detail=detail,
                        )
                    )

            if synth_ask > 0 and direct_bid > 0:
                gross_bps = ((direct_bid / synth_ask) - 1.0) * 10_000
                maybe_add(
                    gross_bps,
                    [f"BUY {base} via BTC", f"SELL {usdt_sym}"],
                    [
                        {"symbol": "BTCUSDT", "side": "BUY", "price": btc.ask},
                        {"symbol": sym, "side": "BUY", "price": quote.ask},
                        {"symbol": usdt_sym, "side": "SELL", "price": direct_bid},
                    ],
                    f"{base}: synth ask {synth_ask:.6f} vs direct bid {direct_bid:.6f}",
                    quote.ask_qty * synth_ask if quote.ask_qty else self.max_position_usd,
                )

            if direct_ask > 0 and synth_bid > 0:
                gross_bps = ((synth_bid / direct_ask) - 1.0) * 10_000
                maybe_add(
                    gross_bps,
                    [f"BUY {usdt_sym}", f"SELL {base} via BTC"],
                    [
                        {"symbol": usdt_sym, "side": "BUY", "price": direct_ask},
                        {"symbol": sym, "side": "SELL", "price": quote.bid},
                        {"symbol": "BTCUSDT", "side": "SELL", "price": btc.bid},
                    ],
                    f"{base}: direct ask {direct_ask:.6f} vs synth bid {synth_bid:.6f}",
                    usdt_q.ask_qty * direct_ask
                    if usdt_q.ask_qty
                    else self.max_position_usd,
                )

        return results
