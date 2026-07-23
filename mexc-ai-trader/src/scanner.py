"""24/7 MEXC Futures market scanner."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from config import Settings
from src.analysis.engine import analyze_symbol, format_report
from src.analysis.fundamentals import analyze_fundamentals
from src.mexc_client import MexcFuturesClient
from src.models import SignalReport
from src.telegram_alerter import TelegramAlerter

logger = logging.getLogger(__name__)


class MarketScanner:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = MexcFuturesClient(
            base_url=settings.mexc_base_url,
            min_request_interval=settings.request_gap_seconds,
        )
        self.telegram = TelegramAlerter(settings.telegram_bot_token, settings.telegram_chat_id)
        self._last_alerted: dict[str, float] = {}
        self._alert_cooldown_sec = 60 * 60  # 1h per symbol direction

    def _fetch_frames(self, symbol: str) -> dict[str, Any]:
        frames = {}
        for tf in self.settings.timeframes:
            try:
                frames[tf] = self.client.get_klines(symbol, interval=tf, limit=self.settings.kline_limit)
            except Exception as exc:  # noqa: BLE001
                logger.warning("%s %s klines failed: %s", symbol, tf, exc)
        return frames

    def analyze_one(self, symbol: str, fundamentals_cache=None) -> SignalReport | None:
        try:
            frames = self._fetch_frames(symbol)
            if len(frames) < 2:
                return None
            ticker = self.client.get_ticker(symbol)
            if isinstance(ticker, list):
                ticker = ticker[0] if ticker else {}
            deals: list = []
            if self.settings.fetch_deals:
                try:
                    deals = self.client.get_deals(symbol, limit=80)
                except Exception:  # noqa: BLE001
                    deals = []
            return analyze_symbol(
                symbol,
                frames,
                ticker=ticker if isinstance(ticker, dict) else {},
                deals=deals,
                settings=self.settings,
                fundamentals_cache=fundamentals_cache,
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

    def run_scan(self) -> list[SignalReport]:
        symbols = self.client.list_usdt_perpetuals(self.settings.symbol_whitelist or None)
        logger.info("Scanning %d MEXC USDT perpetual contracts", len(symbols))
        fundamentals = analyze_fundamentals(self.settings.newsapi_key, symbol="BTC_USDT")
        results: list[SignalReport] = []

        with ThreadPoolExecutor(max_workers=self.settings.max_workers) as pool:
            futures = {
                pool.submit(self.analyze_one, symbol, fundamentals): symbol for symbol in symbols
            }
            for fut in as_completed(futures):
                symbol = futures[fut]
                try:
                    report = fut.result()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Worker error %s: %s", symbol, exc)
                    continue
                if report is None:
                    continue
                results.append(report)
                if self._should_alert(report):
                    text = format_report(report)
                    logger.info("ALERT %s %s conf=%.1f", report.symbol, report.verdict.value, report.confidence)
                    self.telegram.send(text)
                elif report.confidence >= 70:
                    logger.info(
                        "%s -> %s (%.1f%%) — %s",
                        report.symbol,
                        report.verdict.value,
                        report.confidence,
                        report.message,
                    )
        return results

    def run_forever(self) -> None:
        logger.info(
            "Starting 24/7 scanner | interval=%ss | min_confidence=%s",
            self.settings.scan_interval_seconds,
            self.settings.min_confidence,
        )
        if not self.telegram.enabled:
            logger.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing — alerts print to console")
        while True:
            started = time.time()
            try:
                self.run_scan()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Scan cycle failed: %s", exc)
                self.telegram.send(f"⚠️ MEXC scanner error: {exc}")
            elapsed = time.time() - started
            sleep_for = max(5, self.settings.scan_interval_seconds - int(elapsed))
            logger.info("Cycle done in %.1fs — sleeping %ss", elapsed, sleep_for)
            time.sleep(sleep_for)
