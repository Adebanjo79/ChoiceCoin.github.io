from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import Web3

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MintWallet:
    account: LocalAccount
    label: str = ""
    source: str = "env"  # env | telegram

    @property
    def address(self) -> str:
        return self.account.address

    @property
    def private_key(self) -> str:
        return self.account.key.hex()


class WalletStore:
    """Merge PRIVATE_KEYS from env with Telegram-managed mint_wallets.json."""

    def __init__(self, env_keys: list[str], path: Path):
        self.path = path
        self._lock = threading.RLock()
        self._env_keys = list(env_keys)
        self._extra: list[dict[str, str]] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._extra = []
            return
        try:
            data = json.loads(self.path.read_text())
            if isinstance(data, list):
                self._extra = [x for x in data if isinstance(x, dict) and x.get("private_key")]
            else:
                self._extra = []
        except Exception:
            logger.exception("Failed to load %s", self.path)
            self._extra = []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._extra, indent=2) + "\n")
        tmp.replace(self.path)

    def all(self) -> list[MintWallet]:
        with self._lock:
            out: list[MintWallet] = []
            seen: set[str] = set()
            for key in self._env_keys:
                try:
                    acct = Account.from_key(key if key.startswith("0x") else "0x" + key)
                except Exception:
                    continue
                if acct.address.lower() in seen:
                    continue
                seen.add(acct.address.lower())
                out.append(MintWallet(account=acct, source="env"))
            for item in self._extra:
                key = item.get("private_key", "")
                try:
                    acct = Account.from_key(key if key.startswith("0x") else "0x" + key)
                except Exception:
                    continue
                if acct.address.lower() in seen:
                    continue
                seen.add(acct.address.lower())
                out.append(
                    MintWallet(
                        account=acct,
                        label=str(item.get("label") or ""),
                        source="telegram",
                    )
                )
            return out

    def addresses(self) -> list[str]:
        return [w.address for w in self.all()]

    def add(self, private_key: str, label: str = "") -> MintWallet:
        key = private_key.strip()
        if not key.startswith("0x"):
            key = "0x" + key
        acct = Account.from_key(key)
        with self._lock:
            for w in self.all():
                if w.address.lower() == acct.address.lower():
                    raise ValueError(f"Wallet already present: {acct.address}")
            self._extra.append({"private_key": key, "label": label, "address": acct.address})
            self._save()
            return MintWallet(account=acct, label=label, source="telegram")

    def remove(self, address: str) -> bool:
        target = Web3.to_checksum_address(address).lower()
        with self._lock:
            before = len(self._extra)
            self._extra = [
                x
                for x in self._extra
                if Account.from_key(
                    x["private_key"] if x["private_key"].startswith("0x") else "0x" + x["private_key"]
                ).address.lower()
                != target
            ]
            # Also block removing env wallets via file — return False if only in env
            remaining_env = any(
                Account.from_key(k if k.startswith("0x") else "0x" + k).address.lower() == target
                for k in self._env_keys
            )
            if len(self._extra) == before and remaining_env:
                raise ValueError("That wallet comes from PRIVATE_KEYS in .env — remove it there.")
            if len(self._extra) == before:
                return False
            self._save()
            return True


def provider_label(url: str) -> str:
    """Label RPC by real host (Alchemy / Chainstack / Ink public / other)."""
    host = (urlparse(url).hostname or url).lower()
    if "alchemy" in host:
        return "Alchemy"
    if "chainstack" in host:
        return "Chainstack"
    if "ankr" in host:
        return "Ankr"
    if "quicknode" in host or "quiknode" in host:
        return "QuickNode"
    if "inkonchain.com" in host:
        if "rpc-gel" in host:
            return "Ink public (gel)"
        if "rpc-qnd" in host:
            return "Ink public (qnd)"
        return "Ink public"
    if "llama" in host:
        return "LlamaNodes"
    return host


@dataclass
class RpcEndpoint:
    url: str
    label: str
    hold_until: float = 0.0
    failures: int = 0


class RateLimiter:
    def __init__(self, rate_per_sec: float):
        self.interval = 1.0 / max(rate_per_sec * 0.8, 0.1)  # ~80% of configured limit
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if now < self._next:
                time.sleep(self._next - now)
                now = time.monotonic()
            self._next = now + self.interval


class RpcPool:
    """
    Multi-RPC client with failover on 429 / dead node / garbled non-UTF-8 bodies.
    After garbled primary replies, hold backup a few minutes; failback only after a
    full eth_getBlockByNumber(latest, true) probe.
    """

    HOLD_SECONDS = 180.0

    def __init__(
        self,
        urls: list[str],
        chain_id: int,
        rate_limit: float = 25.0,
        load_balance: bool = False,
        on_alert: Any | None = None,
    ):
        if not urls:
            raise ValueError("At least one RPC URL required")
        self.chain_id = chain_id
        self.load_balance = load_balance
        self.on_alert = on_alert
        self.limiter = RateLimiter(rate_limit)
        self.endpoints = [RpcEndpoint(url=u, label=provider_label(u)) for u in urls]
        self._idx = 0
        self._lock = threading.RLock()
        self._last_alert = 0.0
        self._clients = {e.url: Web3(Web3.HTTPProvider(e.url, request_kwargs={"timeout": 25})) for e in self.endpoints}

    @property
    def primary(self) -> RpcEndpoint:
        return self.endpoints[0]

    def active(self) -> RpcEndpoint:
        with self._lock:
            now = time.monotonic()
            for e in self.endpoints:
                if e.hold_until <= now:
                    return e
            # all held — use least-held
            return min(self.endpoints, key=lambda x: x.hold_until)

    def w3(self, endpoint: RpcEndpoint | None = None) -> Web3:
        ep = endpoint or self.active()
        return self._clients[ep.url]

    def _alert(self, text: str) -> None:
        now = time.monotonic()
        if now - self._last_alert < 45:
            return
        self._last_alert = now
        if self.on_alert:
            try:
                self.on_alert(text)
            except Exception:
                logger.exception("RPC alert callback failed")

    def _is_garbled(self, exc: BaseException) -> bool:
        msg = str(exc).lower()
        if "codec can't decode" in msg or "utf-8" in msg and "decode" in msg:
            return True
        if "unexpected utf" in msg or "invalid utf" in msg:
            return True
        return False

    def _hold(self, ep: RpcEndpoint, reason: str) -> None:
        ep.hold_until = time.monotonic() + self.HOLD_SECONDS
        ep.failures += 1
        self._alert(f"⚠️ RPC failover → holding {ep.label} ({reason}). Using backup.")

    def _try_failback(self) -> None:
        primary = self.primary
        now = time.monotonic()
        if primary.hold_until <= now:
            return
        # Probe full getBlock(latest, true) before failback
        try:
            self.limiter.wait()
            block = self._clients[primary.url].eth.get_block("latest", full_transactions=True)
            if block and block.get("number") is not None:
                primary.hold_until = 0
                primary.failures = 0
                self._alert(f"✅ RPC failback → {primary.label} healthy again.")
        except Exception as exc:
            logger.info("Primary probe still failing (%s): %s", primary.label, exc)

    def call(self, fn_name: str, *args: Any, **kwargs: Any) -> Any:
        self._try_failback()
        last_exc: BaseException | None = None
        order = list(self.endpoints)
        if self.load_balance:
            with self._lock:
                self._idx = (self._idx + 1) % len(order)
                order = order[self._idx :] + order[: self._idx]
        else:
            # prefer non-held, primary first
            now = time.monotonic()
            order = sorted(order, key=lambda e: (e.hold_until > now, e is not self.primary))

        for ep in order:
            if ep.hold_until > time.monotonic() and ep is not order[-1]:
                continue
            try:
                self.limiter.wait()
                eth = self._clients[ep.url].eth
                method = getattr(eth, fn_name)
                return method(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                msg = str(exc).lower()
                if "429" in msg or "too many requests" in msg or "rate limit" in msg:
                    self._alert(f"⚠️ RPC busy ({ep.label}): rate limited")
                    self._hold(ep, "429")
                    continue
                if self._is_garbled(exc):
                    self._hold(ep, "garbled non-UTF-8 body")
                    continue
                if "connection" in msg or "timeout" in msg or "502" in msg or "503" in msg:
                    self._hold(ep, "dead/unreachable")
                    continue
                raise
        assert last_exc is not None
        self._alert(f"❌ All RPCs failed. Last: {last_exc}")
        raise last_exc

    def block_number(self) -> int:
        self._try_failback()
        last_exc: BaseException | None = None
        for ep in self.endpoints:
            if ep.hold_until > time.monotonic() and ep is not self.endpoints[-1]:
                continue
            try:
                self.limiter.wait()
                return int(self._clients[ep.url].eth.block_number)
            except Exception as exc:
                last_exc = exc
                if self._is_garbled(exc) or "429" in str(exc) or "timeout" in str(exc).lower():
                    self._hold(ep, str(exc)[:80])
                    continue
                raise
        raise last_exc  # type: ignore[misc]

    def get_block(self, block_id: Any, full_transactions: bool = False) -> Any:
        return self.call("get_block", block_id, full_transactions)

    def get_transaction_count(self, address: str, block_identifier: str = "pending") -> int:
        return int(self.call("get_transaction_count", address, block_identifier))

    def get_balance(self, address: str) -> int:
        return int(self.call("get_balance", address))

    def send_raw_transaction(self, raw: bytes | str) -> Any:
        return self.call("send_raw_transaction", raw)

    def call_contract(self, tx: dict[str, Any], block: str = "latest") -> Any:
        return self.call("call", tx, block)

    def get_code(self, address: str) -> bytes:
        return self.call("get_code", address)

    def status_line(self) -> str:
        now = time.monotonic()
        parts = []
        for e in self.endpoints:
            state = "HOLD" if e.hold_until > now else "OK"
            parts.append(f"{e.label}:{state}")
        return ", ".join(parts)