from __future__ import annotations

from src.engine.arbitrage import ArbitrageEngine, split_symbol
from src.engine.book import OrderBookCache, Quote
from src.engine.executor import PaperExecutor


def _q(symbol: str, bid: float, ask: float, bid_qty: float = 10, ask_qty: float = 10) -> Quote:
    return Quote(symbol=symbol, bid=bid, ask=ask, bid_qty=bid_qty, ask_qty=ask_qty, ts_ms=1)


def test_split_symbol():
    assert split_symbol("BTCUSDT") == ("BTC", "USDT")
    assert split_symbol("ETHBTC") == ("ETH", "BTC")
    assert split_symbol("PEPEUSDT") == ("PEPE", "USDT")


def test_book_snapshot():
    book = OrderBookCache()
    book.update(_q("BTCUSDT", 100.0, 100.2))
    snap = book.snapshot()
    assert "BTCUSDT" in snap
    assert snap["BTCUSDT"]["mid"] == 100.1


def test_triangular_opportunity_detected():
    book = OrderBookCache()
    # Construct a clear mispricing so forward triangle is profitable before/after fees.
    # USDT -> ETH @ 2000, ETH -> BTC via ETHBTC sell, BTC -> USDT
    book.update(_q("ETHUSDT", 1990.0, 2000.0, bid_qty=5, ask_qty=5))
    book.update(_q("BTCUSDT", 100_000.0, 100_010.0, bid_qty=2, ask_qty=2))
    # Make ETH cheap vs BTC path: selling ETH for lots of BTC
    book.update(_q("ETHBTC", 0.03, 0.0301, bid_qty=20, ask_qty=20))

    engine = ArbitrageEngine(book, taker_fee_bps=10.0, min_edge_bps=1.0, max_position_usd=20)
    engine.build_triangles(["ETHUSDT", "BTCUSDT", "ETHBTC"])
    opps = engine.scan()
    assert any(o.kind == "triangular" for o in opps)
    assert opps[0].net_edge_bps > 0


def test_synthetic_vs_direct():
    book = OrderBookCache()
    book.update(_q("BTCUSDT", 100_000.0, 100_000.0))
    book.update(_q("ETHBTC", 0.03, 0.03))
    # Direct ETH vastly richer than synthetic 0.03 * 100000 = 3000
    book.update(_q("ETHUSDT", 3500.0, 3501.0))
    engine = ArbitrageEngine(book, taker_fee_bps=10.0, min_edge_bps=1.0)
    engine.build_triangles(["ETHUSDT", "BTCUSDT", "ETHBTC"])
    opps = engine.scan()
    kinds = {o.kind for o in opps}
    assert "synthetic_vs_direct" in kinds


def test_paper_executor_books_pnl():
    ex = PaperExecutor(starting_capital_usd=68.0, max_position_usd=25.0, paper_trading=True)
    from src.engine.arbitrage import Opportunity

    opp = Opportunity(
        kind="triangular",
        path=["USDT->ETH", "ETH->BTC", "BTC->USDT"],
        legs=[],
        gross_edge_bps=50,
        net_edge_bps=20,
        notional_usd=20,
        detail="test",
    )
    fill = ex.maybe_execute(opp)
    assert fill is not None
    assert fill.expected_pnl_usd == 0.04  # 20 * 20bps
    assert ex.portfolio.cash_usd == 68.04
    assert ex.portfolio.realized_pnl_usd == 0.04


def test_paper_executor_rejects_zero_edge():
    ex = PaperExecutor(starting_capital_usd=68.0)
    from src.engine.arbitrage import Opportunity

    opp = Opportunity(
        kind="triangular",
        path=["a"],
        legs=[],
        gross_edge_bps=5,
        net_edge_bps=0,
        notional_usd=10,
        detail="none",
    )
    assert ex.maybe_execute(opp) is None
