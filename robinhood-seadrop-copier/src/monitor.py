from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .chain import ChainClient
from .copier import SeaDropCopier, format_copy_report
from .seadrop import DecodedSeaDropMint, decode_seadrop_input
from .telegram_notify import TelegramNotifier

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ObservedMint:
    tx_hash: str
    from_address: str
    to: str
    value: int
    block_number: int
    decoded: DecodedSeaDropMint


class MintMonitor:
    def __init__(
        self,
        chain: ChainClient,
        copier: SeaDropCopier,
        seadrop: str,
        notifier: TelegramNotifier,
        explorer_tx_url: str,
        poll_seconds: float = 2.0,
        lookback_blocks: int = 8,
        state_path: Path | None = None,
        our_addresses: Iterable[str] | None = None,
    ):
        self.chain = chain
        self.copier = copier
        self.seadrop = seadrop.lower()
        self.notifier = notifier
        self.explorer_tx_url = explorer_tx_url
        self.poll_seconds = poll_seconds
        self.lookback_blocks = lookback_blocks
        self.state_path = state_path
        self.our_addresses = {a.lower() for a in (our_addresses or [])}
        self._seen: set[str] = set()
        self._load_state()

    def _load_state(self) -> None:
        if not self.state_path or not self.state_path.exists():
            return
        for line in self.state_path.read_text().splitlines():
            h = line.strip().lower()
            if h:
                self._seen.add(h)

    def _persist_seen(self, tx_hash: str) -> None:
        self._seen.add(tx_hash.lower())
        if not self.state_path:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with self.state_path.open("a") as fh:
            fh.write(tx_hash.lower() + "\n")

    def scan_block(self, block_number: int) -> list[ObservedMint]:
        found: list[ObservedMint] = []
        for tx in self.chain.get_block_transactions(block_number):
            to = (tx.get("to") or "").lower()
            if to != self.seadrop:
                continue
            tx_hash = tx["hash"]
            if tx_hash.lower() in self._seen:
                continue
            if tx["from"].lower() in self.our_addresses:
                self._persist_seen(tx_hash)
                continue
            decoded = decode_seadrop_input(tx["input"])
            if decoded is None:
                continue
            found.append(
                ObservedMint(
                    tx_hash=tx_hash,
                    from_address=tx["from"],
                    to=tx["to"],
                    value=int(tx["value"]),
                    block_number=int(tx["blockNumber"]),
                    decoded=decoded,
                )
            )
        return found

    def handle_mint(self, observed: ObservedMint) -> str:
        self._persist_seen(observed.tx_hash)
        copy = self.copier.copy_mint(observed.decoded)
        report = format_copy_report(
            observed.decoded,
            copy,
            source_tx=observed.tx_hash,
            from_address=observed.from_address,
            block_number=observed.block_number,
            explorer_tx_url=self.explorer_tx_url,
            value_wei=observed.value,
        )
        self.notifier.send(report)
        logger.info(report)
        return report

    def run_forever(self) -> None:
        tip = self.chain.get_block_number()
        cursor = max(0, tip - self.lookback_blocks)
        logger.info("Watching SeaDrop %s from block %s (tip %s)", self.seadrop, cursor, tip)
        while True:
            try:
                tip = self.chain.get_block_number()
                while cursor <= tip:
                    for observed in self.scan_block(cursor):
                        self.handle_mint(observed)
                    cursor += 1
            except Exception:
                logger.exception("Monitor loop error")
            time.sleep(self.poll_seconds)

    def run_once(self, blocks: int | None = None) -> list[str]:
        tip = self.chain.get_block_number()
        start = max(0, tip - (blocks if blocks is not None else self.lookback_blocks))
        reports: list[str] = []
        for bn in range(start, tip + 1):
            for observed in self.scan_block(bn):
                reports.append(self.handle_mint(observed))
        return reports