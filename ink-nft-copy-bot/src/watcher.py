from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from web3 import Web3

from .copy_engine import CopyEngine, CopyOutcome, format_detection, format_results
from .rpc import MintWallet, RpcPool, WalletStore
from .seadrop import KNOWN_MINT_SELECTORS, decode_mint_input

logger = logging.getLogger(__name__)

AlertFn = Callable[[str], None]


@dataclass(frozen=True)
class ObservedTx:
    tx_hash: str
    from_address: str
    to: str
    value: int
    input: str
    block_number: int | str


class MintWatcher:
    """
    Watch target wallets. Never skip blocks — catch up in chunks.
    Start copying before Telegram. Skip receipt fetches for known SeaDrop selectors.
    Optional pending/mempool via WebSocket (OFF by default).
    """

    def __init__(
        self,
        rpc: RpcPool,
        engine: CopyEngine,
        wallets: WalletStore,
        *,
        seadrop: str,
        targets: list[str],
        explorer_tx_url: str,
        poll_interval: float = 0.4,
        catchup_chunk: int = 40,
        pending_detection: bool = False,
        pending_ws_url: str = "",
        state_file: Path | None = None,
        alert: AlertFn | None = None,
        is_paused: Callable[[], bool] | None = None,
    ):
        self.rpc = rpc
        self.engine = engine
        self.wallets = wallets
        self.seadrop = Web3.to_checksum_address(seadrop)
        self._targets = {Web3.to_checksum_address(t).lower() for t in targets}
        self.explorer_tx_url = explorer_tx_url
        self.poll_interval = poll_interval
        self.catchup_chunk = catchup_chunk
        self.pending_detection = pending_detection
        self.pending_ws_url = pending_ws_url
        self.state_file = state_file
        self.alert = alert or (lambda _t: None)
        self.is_paused = is_paused or (lambda: False)
        self._seen: set[str] = set()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._cursor: int | None = None
        self._load_state()

    def set_targets(self, targets: list[str]) -> None:
        self._targets = {Web3.to_checksum_address(t).lower() for t in targets}
        self._save_state()

    @property
    def targets(self) -> list[str]:
        return sorted(self._targets)

    def _load_state(self) -> None:
        if not self.state_file or not self.state_file.exists():
            return
        try:
            data = json.loads(self.state_file.read_text())
            self._cursor = data.get("cursor")
            for h in data.get("seen", [])[-5000:]:
                self._seen.add(str(h).lower())
            if data.get("targets"):
                self._targets = {str(t).lower() for t in data["targets"]}
        except Exception:
            logger.exception("state load failed")

    def _save_state(self) -> None:
        if not self.state_file:
            return
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "cursor": self._cursor,
            "seen": list(self._seen)[-5000:],
            "targets": list(self._targets),
        }
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload))
        tmp.replace(self.state_file)

    def stop(self) -> None:
        self._stop.set()

    def _mark_seen(self, tx_hash: str) -> bool:
        h = tx_hash.lower()
        with self._lock:
            if h in self._seen:
                return False
            self._seen.add(h)
            return True

    def handle_tx(self, obs: ObservedTx, *, pending: bool = False) -> CopyOutcome | None:
        if obs.from_address.lower() not in self._targets:
            return None
        if not self._mark_seen(obs.tx_hash):
            return None
        if self.is_paused():
            self.alert(f"⏸ Paused — saw target mint {obs.tx_hash} but did not copy.")
            return None

        our = {a.lower() for a in self.wallets.addresses()}
        if obs.from_address.lower() in our:
            return None

        decoded = decode_mint_input(
            obs.input, to=obs.to or "0x0000000000000000000000000000000000000000", value=obs.value, seadrop=self.seadrop
        )
        if decoded is None:
            # Unknown interaction — if value=0 to a contract, still alert lightly
            return None

        # Skip receipt fetch for known SeaDrop mint selectors (already decoded from input)
        _ = KNOWN_MINT_SELECTORS.get(decoded.selector)

        hint = {
            "mintPublic": "SeaDrop free/public candidate",
            "mintSigned": "SeaDrop mintSigned (not copyable)",
            "mintAllowList": "SeaDrop allowlist (not copyable)",
            "mintAllowedTokenHolder": "SeaDrop token-gated (not copyable)",
            "direct": "Direct mint/claim candidate",
        }.get(decoded.method, decoded.method)

        name = self.engine.collection_name(decoded.nft_contract)

        # COPY FIRST — Telegram after
        mint_wallets = self.wallets.all()
        outcome = self.engine.copy(decoded, mint_wallets, their_from=obs.from_address)

        detection = format_detection(
            collection_name=name,
            decoded=decoded,
            from_address=obs.from_address,
            block=("pending" if pending else obs.block_number),
            source_tx=obs.tx_hash,
            explorer_tx_url=self.explorer_tx_url,
            hint=hint + (" [pending]" if pending else ""),
        )
        results = format_results(outcome, self.explorer_tx_url)
        self.alert(detection + "\n\n" + results)
        self._save_state()
        return outcome

    def scan_block(self, block_number: int) -> int:
        block = self.rpc.get_block(block_number, full_transactions=True)
        count = 0
        for tx in block["transactions"]:
            frm = tx["from"]
            if Web3.to_checksum_address(frm).lower() not in self._targets:
                continue
            to = tx["to"]
            if to is None:
                continue
            raw_in = tx["input"]
            if hasattr(raw_in, "hex"):
                raw_in = raw_in.hex()
            h = tx["hash"]
            if hasattr(h, "hex"):
                h = h.hex()
            obs = ObservedTx(
                tx_hash=h if h.startswith("0x") else "0x" + h,
                from_address=Web3.to_checksum_address(frm),
                to=Web3.to_checksum_address(to),
                value=int(tx["value"]),
                input=raw_in if str(raw_in).startswith("0x") else "0x" + str(raw_in),
                block_number=block_number,
            )
            if self.handle_tx(obs):
                count += 1
        return count

    def run_forever(self) -> None:
        tip = self.rpc.block_number()
        if self._cursor is None:
            self._cursor = tip
        logger.info("Watcher start cursor=%s tip=%s targets=%s", self._cursor, tip, len(self._targets))

        pending_thread = None
        if self.pending_detection and self.pending_ws_url:
            pending_thread = threading.Thread(target=self._pending_loop, daemon=True)
            pending_thread.start()

        while not self._stop.is_set():
            try:
                tip = self.rpc.block_number()
                while self._cursor is not None and self._cursor <= tip and not self._stop.is_set():
                    end = min(self._cursor + self.catchup_chunk - 1, tip)
                    for bn in range(self._cursor, end + 1):
                        self.scan_block(bn)
                        self._cursor = bn + 1
                    self._save_state()
            except Exception:
                logger.exception("watcher loop error")
            self._stop.wait(self.poll_interval)

    def _pending_loop(self) -> None:
        """Optional — pending txs can fail and waste gas."""
        try:
            import websockets
        except ImportError:
            logger.error("websockets not installed; pending detection disabled")
            return

        async def _run() -> None:
            while not self._stop.is_set():
                try:
                    async with websockets.connect(self.pending_ws_url, ping_interval=20) as ws:
                        await ws.send(
                            json.dumps(
                                {
                                    "jsonrpc": "2.0",
                                    "id": 1,
                                    "method": "eth_subscribe",
                                    "params": ["newPendingTransactions"],
                                }
                            )
                        )
                        await ws.recv()
                        while not self._stop.is_set():
                            msg = json.loads(await ws.recv())
                            tx_hash = msg.get("params", {}).get("result")
                            if not tx_hash:
                                continue
                            try:
                                tx = self.rpc.call("get_transaction", tx_hash)
                            except Exception:
                                continue
                            if not tx or not tx.get("from") or not tx.get("to"):
                                continue
                            if Web3.to_checksum_address(tx["from"]).lower() not in self._targets:
                                continue
                            raw_in = tx["input"]
                            if hasattr(raw_in, "hex"):
                                raw_in = raw_in.hex()
                            obs = ObservedTx(
                                tx_hash=tx_hash,
                                from_address=Web3.to_checksum_address(tx["from"]),
                                to=Web3.to_checksum_address(tx["to"]),
                                value=int(tx["value"]),
                                input=raw_in if str(raw_in).startswith("0x") else "0x" + raw_in,
                                block_number="pending",
                            )
                            self.handle_tx(obs, pending=True)
                except Exception:
                    logger.exception("pending ws error; retrying")
                    await asyncio.sleep(3)

        asyncio.run(_run())