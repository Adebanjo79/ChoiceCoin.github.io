"""24/7 MEXC Spot market scanner."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

from config import Settings
from src.analysis.engine import analyze_symbol, format_report
from src.analysis.fundamentals import analyze_fundamentals
from src.mexc_client import MexcSpotClient, normalize_spot_symbol
from src.models import SignalReport
from src.runtime_status import RUNTIME
from src.telegram_alerter import TelegramAlerter

logger = logging.getLogger(__name__)


class MarketScanner:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = MexcSpotClient(
            base_url=settings.mexc_base_url,
            min_request_interval=settings.request_gap_seconds,
        )
        self.telegram = TelegramAlerter(settings.telegram_bot_token, settings.telegram_chat_id)
        self._last_alerted: dict[str, float] = {}
        self._alert_cooldown_sec = 60 * 60  # 1h per symbol direction
        self._cycle = 0
        RUNTIME.update(
            mode=settings.scan_mode,
            min_confidence=settings.min_confidence,
            phase="starting",
        )

    def _status(self, text: str) -> None:
        if self.settings.telegram_status and self.telegram.enabled:
            self.telegram.send(text)

    def _fetch_frames(self, symbol: str) -> dict[str, Any]:
        frames = {}
        for tf in self.settings.active_timeframes():
            try:
                frames[tf] = self.client.get_klines(symbol, interval=tf, limit=self.settings.kline_limit)
            except Exception as exc:  # noqa: BLE001
                logger.warning("%s %s klines failed: %s", symbol, tf, exc)
        return frames

    def analyze_one(
        self,
        symbol: str,
        fundamentals_cache=None,
        ticker_cache: dict[str, Any] | None = None,
        btc_df=None,
    ) -> SignalReport | None:
        try:
            symbol = normalize_spot_symbol(symbol)
            frames = self._fetch_frames(symbol)
            if len(frames) < 2:
                return None
            ticker: dict[str, Any]
            if ticker_cache and symbol in ticker_cache:
                ticker = ticker_cache[symbol]
            else:
                raw = self.client.get_ticker_24h(symbol)
                ticker = raw[0] if isinstance(raw, list) and raw else (raw if isinstance(raw, dict) else {})
            deals: list = []
            if self.settings.fetch_deals:
                try:
                    deals = self.client.get_trades(symbol, limit=80)
                except Exception:  # noqa: BLE001
                    deals = []
            depth = None
            if self.settings.fetch_depth:
                try:
                    depth = self.client.get_depth(symbol, limit=50)
                except Exception:  # noqa: BLE001
                    depth = None
            if btc_df is None:
                try:
                    btc_df = self.client.get_klines(
                        "BTCUSDT", interval="Min15", limit=self.settings.kline_limit
                    )
                except Exception:  # noqa: BLE001
                    btc_df = None
            return analyze_symbol(
                symbol,
                frames,
                ticker=ticker,
                deals=deals,
                settings=self.settings,
                fundamentals_cache=fundamentals_cache,
                btc_df=btc_df,
                depth=depth,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Analyze failed for %s: %s", symbol, exc)
            return None

    def _should_alert(self, report: SignalReport) -> bool:
        if not report.is_actionable():
            return False
        key = f"{report.symbol}:{report.direction.value}"
        now = time.time()
        last = self._last_alerted.get(key, 0)
        if now - last < self._alert_cooldown_sec:
            return False
        self._last_alerted[key] = now
        return True

    def _select_symbols(self) -> tuple[list[str], dict[str, dict[str, Any]], int]:
        """Return symbols to analyze, ticker cache, and total spot pair count."""
        all_symbols = self.client.list_usdt_spot_pairs(self.settings.symbol_whitelist or None)
        total = len(all_symbols)

        tickers_raw = self.client.get_ticker_24h()
        ticker_list = tickers_raw if isinstance(tickers_raw, list) else [tickers_raw]
        ticker_cache: dict[str, dict[str, Any]] = {}
        for t in ticker_list:
            if isinstance(t, dict) and t.get("symbol"):
                ticker_cache[normalize_spot_symbol(str(t["symbol"]))] = t

        # Rank every USDT pair by 24h quote volume (liquidity), then move strength
        ranked: list[tuple[float, float, str]] = []
        for symbol in all_symbols:
            t = ticker_cache.get(symbol, {})
            turnover = float(t.get("quoteVolume") or t.get("amount24") or 0)
            try:
                move = abs(float(t.get("priceChangePercent") or 0))
            except (TypeError, ValueError):
                move = 0.0
            ranked.append((turnover, move, symbol))

        ranked.sort(key=lambda x: (x[0], x[1]), reverse=True)
        top_n = self.settings.scan_top_n if self.settings.scan_top_n > 0 else len(ranked)
        min_turn = self.settings.min_turnover_usdt

        # Prefer pairs above turnover floor, but ALWAYS fill up to top_n by liquidity
        liquid = [s for turn, _, s in ranked if min_turn <= 0 or turn >= min_turn]
        if len(liquid) >= top_n:
            symbols = liquid[:top_n]
        else:
            # Not enough pairs met the floor — take the most liquid top_n overall
            symbols = [s for _, _, s in ranked[:top_n]]
            logger.info(
                "Only %d pairs met turnover>=%.0f USDT; scanning top %d by liquidity instead",
                len(liquid),
                min_turn,
                len(symbols),
            )

        if not symbols:
            logger.warning("No spot symbols available — empty market list")
            symbols = all_symbols[:top_n] if top_n else all_symbols

        return symbols, ticker_cache, total

    def run_scan(self) -> list[SignalReport]:
        symbols, ticker_cache, total_all = self._select_symbols()
        total = len(symbols)
        tfs = ", ".join(self.settings.active_timeframes())
        logger.info(
            "Scanning %d/%d spot pairs | mode=%s | tfs=%s | workers=%s | account=%.0f USDT | target upside=%.0f%%",
            total,
            total_all,
            self.settings.scan_mode,
            tfs,
            self.settings.max_workers,
            self.settings.account_balance_usdt,
            self.settings.target_upside_pct,
        )
        RUNTIME.update(
            phase="scanning",
            cycle=self._cycle,
            mode=self.settings.scan_mode,
            min_confidence=self.settings.min_confidence,
            total_market=total_all,
            scan_target=total,
            done=0,
            signals_this_cycle=0,
            cycle_started_at=time.time(),
            waiting_until=0.0,
            last_error="",
        )
        self._status(
            f"🔎 Spot scan started\n"
            f"Analyzing: {total} of {total_all} USDT pairs\n"
            f"Mode: {self.settings.scan_mode}\n"
            f"Account: {self.settings.account_balance_usdt:.0f} USDT | TP3 aim ≈{self.settings.target_upside_pct:.0f}%\n"
            f"Min confidence: {self.settings.min_confidence}%\n"
            f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        )

        fundamentals = analyze_fundamentals(self.settings.newsapi_key, symbol="BTCUSDT")
        btc_df = None
        try:
            btc_df = self.client.get_klines("BTCUSDT", interval="Min15", limit=self.settings.kline_limit)
        except Exception as exc:  # noqa: BLE001
            logger.warning("BTC volatility frame failed: %s", exc)

        results: list[SignalReport] = []
        actionable = 0
        done = 0
        every = max(10, self.settings.status_progress_every)

        with ThreadPoolExecutor(max_workers=self.settings.max_workers) as pool:
            futures = {
                pool.submit(self.analyze_one, symbol, fundamentals, ticker_cache, btc_df): symbol
                for symbol in symbols
            }
            for fut in as_completed(futures):
                symbol = futures[fut]
                done += 1
                RUNTIME.update(done=done, last_symbol=symbol)
                try:
                    report = fut.result()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Worker error %s: %s", symbol, exc)
                    continue
                if report is None:
                    if done % every == 0 or done == total:
                        self._status(f"⏳ Still working… {done}/{total} spot pairs checked")
                    continue
                results.append(report)
                if self._should_alert(report):
                    actionable += 1
                    RUNTIME.update(
                        signals_this_cycle=actionable,
                        last_signal=f"{report.symbol} {report.verdict.value} {report.confidence:.1f}%",
                    )
                    text = format_report(report)
                    logger.info(
                        "ALERT %s %s conf=%.1f",
                        report.symbol,
                        report.verdict.value,
                        report.confidence,
                    )
                    self.telegram.send(text)
                elif report.confidence >= 70:
                    logger.info(
                        "%s -> %s (%.1f%%) — %s",
                        report.symbol,
                        report.verdict.value,
                        report.confidence,
                        report.message,
                    )

                near = sorted(results, key=lambda r: r.confidence, reverse=True)[:3]
                RUNTIME.update(
                    signals_this_cycle=actionable,
                    closest=[f"{r.symbol}: {r.confidence:.1f}% ({r.verdict.value})" for r in near],
                )

                if done % every == 0 or done == total:
                    self._status(
                        f"⏳ Progress: {done}/{total} pairs\n"
                        f"Spot signals sent this cycle: {actionable}"
                    )

        near = sorted(
            [r for r in results if not r.is_actionable()],
            key=lambda r: r.confidence,
            reverse=True,
        )[:3]
        near_lines = [
            f"{r.symbol}: {r.confidence:.1f}% ({r.verdict.value})" for r in near
        ] or ["none"]
        RUNTIME.update(closest=near_lines, done=total, signals_this_cycle=actionable)

        self._status(
            f"✅ Spot scan finished\n"
            f"Checked: {len(results)}/{total}\n"
            f"Signals sent: {actionable}\n"
            f"Closest (not enough yet):\n" + "\n".join(f"• {x}" for x in near_lines)
        )
        return results

    def run_forever(self) -> None:
        logger.info(
            "Starting 24/7 SPOT scanner | interval=%ss | min_confidence=%s | mode=%s | balance=%.0f",
            self.settings.scan_interval_seconds,
            self.settings.min_confidence,
            self.settings.scan_mode,
            self.settings.account_balance_usdt,
        )
        if not self.telegram.enabled:
            logger.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing — alerts print to console")
        else:
            self.telegram.start_command_listener(RUNTIME.format_message)
            # Quiet mode: no ONLINE/scan spam. User types status; signals send automatically.
            logger.info(
                "Telegram quiet mode: spot signals only + on-demand status (type status in chat)"
            )
        while True:
            self._cycle += 1
            started = time.time()
            try:
                self.run_scan()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Scan cycle failed: %s", exc)
                RUNTIME.update(phase="error", last_error=str(exc))
                self.telegram.send(f"⚠️ MEXC spot scanner error: {exc}")
            elapsed = time.time() - started
            sleep_for = max(5, self.settings.scan_interval_seconds - int(elapsed))
            logger.info("Cycle done in %.1fs — sleeping %ss", elapsed, sleep_for)
            RUNTIME.update(phase="waiting", waiting_until=time.time() + sleep_for)
            self._status(
                f"😴 Waiting {sleep_for // 60}m {sleep_for % 60}s until next scan\n"
                f"Cycle #{self._cycle} finished in {int(elapsed)}s\n"
                "Bot is still running."
            )
            time.sleep(sleep_for)
