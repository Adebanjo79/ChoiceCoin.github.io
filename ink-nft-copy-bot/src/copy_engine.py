from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable

from eth_account.signers.local import LocalAccount
from web3 import Web3

from .rpc import MintWallet, RpcPool
from .seadrop import (
    DecodedMint,
    classify_skip,
    decode_revert_reason,
    fetch_collection_name,
    fetch_public_drop,
    rewrite_mint_public,
    try_adapt_direct_calldata,
)

logger = logging.getLogger(__name__)


@dataclass
class WalletOutcome:
    address: str
    ok: bool
    detail: str
    tx_hash: str | None = None


@dataclass
class CopyOutcome:
    decoded: DecodedMint
    collection_name: str
    skip_reason: str | None
    results: list[WalletOutcome] = field(default_factory=list)
    strategy: str = ""

    @property
    def ok_count(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if not r.ok)


class CopyEngine:
    """
    Free SeaDrop mintPublic blast:
      - one window/price check
      - no per-wallet eth_call on live path
      - prefetch balances + pending nonces
      - sign locally, sendRawTransaction in parallel
      - on nonce too low: refresh, re-sign, retry once
    """

    def __init__(
        self,
        rpc: RpcPool,
        seadrop: str,
        *,
        dry_run: bool = True,
        free_mints_only: bool = True,
        gas_limit: int = 350_000,
        max_fee_gwei: float = 5.0,
        max_priority_fee_gwei: float = 1.0,
        chain_id: int = 57073,
    ):
        self.rpc = rpc
        self.seadrop = Web3.to_checksum_address(seadrop)
        self.dry_run = dry_run
        self.free_mints_only = free_mints_only
        self.gas_limit = gas_limit
        self.max_fee_gwei = max_fee_gwei
        self.max_priority_fee_gwei = max_priority_fee_gwei
        self.chain_id = chain_id
        self._name_cache: dict[str, str] = {}
        self._nonce_cache: dict[str, int] = {}
        self._balance_cache: dict[str, int] = {}
        self._cache_ts = 0.0

    def collection_name(self, nft: str) -> str:
        key = nft.lower()
        if key in self._name_cache:
            return self._name_cache[key]
        name = fetch_collection_name(self.rpc.w3(), nft)
        self._name_cache[key] = name
        return name

    def prefetch(self, wallets: list[MintWallet]) -> None:
        for w in wallets:
            addr = w.address
            try:
                self._nonce_cache[addr.lower()] = self.rpc.get_transaction_count(addr, "pending")
                self._balance_cache[addr.lower()] = self.rpc.get_balance(addr)
            except Exception:
                logger.exception("prefetch failed for %s", addr)
        self._cache_ts = time.time()

    def copy(
        self,
        decoded: DecodedMint,
        wallets: list[MintWallet],
        *,
        their_from: str,
        now_ts: int | None = None,
    ) -> CopyOutcome:
        now = int(now_ts if now_ts is not None else time.time())
        name = self.collection_name(decoded.nft_contract) if decoded.nft_contract else "unknown"
        public = None
        if decoded.method == "mintPublic":
            try:
                public = fetch_public_drop(self.rpc.w3(), self.seadrop, decoded.nft_contract)
            except Exception as exc:
                return CopyOutcome(
                    decoded=decoded,
                    collection_name=name,
                    skip_reason=f"Skipped: getPublicDrop failed ({exc})",
                    strategy="none",
                )

        skip = classify_skip(
            decoded, free_mints_only=self.free_mints_only, public=public, now_ts=now
        )
        if skip:
            return CopyOutcome(
                decoded=decoded,
                collection_name=name,
                skip_reason=skip,
                strategy="skip",
            )

        if not wallets:
            return CopyOutcome(
                decoded=decoded,
                collection_name=name,
                skip_reason="Skipped: no minting wallets configured",
                strategy="none",
            )

        # Prefetch once per blast
        self.prefetch(wallets)

        if decoded.method == "mintPublic":
            assert public is not None
            qty = max(1, int(decoded.quantity))
            if public.max_total_mintable_by_wallet > 0:
                qty = min(qty, public.max_total_mintable_by_wallet)
            data = rewrite_mint_public(decoded.nft_contract, decoded.fee_recipient, qty)
            value = 0 if self.free_mints_only else int(public.mint_price) * qty
            to = self.seadrop
            strategy = "mintPublic-free" if value == 0 else "mintPublic-paid"
            return self._blast(
                wallets,
                to=to,
                data=data,
                value=value,
                decoded=decoded,
                collection_name=name,
                strategy=strategy,
                per_wallet_data=None,
                their_from=their_from,
            )

        # Direct free mint — only if calldata can be adapted uniquely per wallet
        strategy = "direct-adapt"
        per_wallet: dict[str, str] = {}
        for w in wallets:
            adapted = try_adapt_direct_calldata(decoded.raw_input, w.address, their_from)
            if adapted is None:
                return CopyOutcome(
                    decoded=decoded,
                    collection_name=name,
                    skip_reason="Skipped: direct mint calldata cannot be safely adapted to our wallet",
                    strategy="skip",
                )
            per_wallet[w.address.lower()] = adapted
        return self._blast(
            wallets,
            to=decoded.mint_contract,
            data="",
            value=0,
            decoded=decoded,
            collection_name=name,
            strategy=strategy,
            per_wallet_data=per_wallet,
            their_from=their_from,
        )

    def _blast(
        self,
        wallets: list[MintWallet],
        *,
        to: str,
        data: str,
        value: int,
        decoded: DecodedMint,
        collection_name: str,
        strategy: str,
        per_wallet_data: dict[str, str] | None,
        their_from: str,
    ) -> CopyOutcome:
        results: list[WalletOutcome] = []
        with ThreadPoolExecutor(max_workers=max(1, len(wallets))) as pool:
            futs = {
                pool.submit(
                    self._send_one,
                    w,
                    to=to,
                    data=(per_wallet_data or {}).get(w.address.lower(), data),
                    value=value,
                ): w
                for w in wallets
            }
            for fut in as_completed(futs):
                results.append(fut.result())
        results.sort(key=lambda r: r.address.lower())
        return CopyOutcome(
            decoded=decoded,
            collection_name=collection_name,
            skip_reason=None,
            results=results,
            strategy=strategy,
        )

    def _send_one(self, wallet: MintWallet, *, to: str, data: str, value: int) -> WalletOutcome:
        addr = wallet.address
        try:
            if self.dry_run:
                # Single shared simulation style check without per-wallet blast eth_call flood:
                # still do one eth_call in dry-run for honesty.
                self.rpc.call_contract(
                    {
                        "from": addr,
                        "to": Web3.to_checksum_address(to),
                        "data": data,
                        "value": int(value),
                    }
                )
                return WalletOutcome(addr, True, "dry-run ok (eth_call)", tx_hash="dry-run")

            nonce = self._nonce_cache.get(addr.lower())
            if nonce is None:
                nonce = self.rpc.get_transaction_count(addr, "pending")
            tx_hash = self._sign_and_send(wallet.account, to, data, value, nonce)
            self._nonce_cache[addr.lower()] = nonce + 1
            return WalletOutcome(addr, True, "sent", tx_hash=tx_hash)
        except Exception as exc:
            msg = str(exc)
            if "nonce too low" in msg.lower() or "already known" in msg.lower():
                try:
                    nonce = self.rpc.get_transaction_count(addr, "pending")
                    tx_hash = self._sign_and_send(wallet.account, to, data, value, nonce)
                    self._nonce_cache[addr.lower()] = nonce + 1
                    return WalletOutcome(addr, True, "sent (nonce retry)", tx_hash=tx_hash)
                except Exception as exc2:
                    return WalletOutcome(addr, False, f"nonce retry failed: {exc2}")
            # Try extract revert data
            reason = decode_revert_reason(getattr(exc, "data", None) or msg)
            if "sold out" in msg.lower() or "max total" in msg.lower():
                reason = "sold out / per-wallet cap"
            return WalletOutcome(addr, False, reason if reason != "revert" else msg[:160])

    def _sign_and_send(
        self,
        account: LocalAccount,
        to: str,
        data: str,
        value: int,
        nonce: int,
    ) -> str:
        w3 = self.rpc.w3()
        tx = {
            "from": account.address,
            "to": Web3.to_checksum_address(to),
            "data": data,
            "value": int(value),
            "nonce": int(nonce),
            "gas": int(self.gas_limit),
            "chainId": int(self.chain_id),
            "type": 2,
            "maxFeePerGas": w3.to_wei(self.max_fee_gwei, "gwei"),
            "maxPriorityFeePerGas": w3.to_wei(self.max_priority_fee_gwei, "gwei"),
        }
        signed = account.sign_transaction(tx)
        raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        h = self.rpc.send_raw_transaction(raw)
        return h.hex() if hasattr(h, "hex") else str(h)


def collapse_identical_skips(results: list[WalletOutcome]) -> list[str]:
    """Collapse identical skip/fail reasons into one line when all match."""
    if not results:
        return []
    fails = [r for r in results if not r.ok]
    if len(fails) >= 2 and len({r.detail for r in fails}) == 1:
        return [f"❌ all {len(fails)} wallets: {fails[0].detail}"]
    lines = []
    for r in results:
        mark = "✅" if r.ok else "❌"
        extra = f" {r.tx_hash}" if r.tx_hash and r.tx_hash != "dry-run" else ""
        short = f"{r.address[:6]}…{r.address[-4:]}"
        lines.append(f"{mark} {short}: {r.detail}{extra}")
    return lines


def format_detection(
    *,
    collection_name: str,
    decoded: DecodedMint,
    from_address: str,
    block: int | str,
    source_tx: str,
    explorer_tx_url: str,
    hint: str,
) -> str:
    src = (
        f"{explorer_tx_url}{source_tx}"
        if explorer_tx_url.endswith("/")
        else f"{explorer_tx_url.rstrip('/')}/{source_tx}"
    )
    return "\n".join(
        [
            "👀 Target mint activity",
            f"From: {from_address}",
            f"Block: {block}",
            f"Collection: {collection_name}",
            f"Collection contract: {decoded.nft_contract}",
            f"Mint contract: {decoded.mint_contract}",
            f"Method: {decoded.method}",
            f"Value: {decoded.value / 1e18:g} ETH",
            f"Hint: {hint}",
            f"Source: {src}",
        ]
    )


def format_results(outcome: CopyOutcome, explorer_tx_url: str) -> str:
    if outcome.skip_reason:
        return f"Copying… skipped.\n\n{outcome.skip_reason}"
    lines = [
        f"Strategy: {outcome.strategy}",
        f"Minting wallets: {len(outcome.results)} (parallel)",
        "Copying…",
        "",
        f"Done: {outcome.ok_count} ok, {outcome.fail_count} failed "
        f"(tried {len(outcome.results)} wallets).",
        "",
    ]
    for line in collapse_identical_skips(outcome.results):
        # attach explorer links for ok hashes
        if "0x" in line and explorer_tx_url:
            # leave hash as-is; optional enrich
            pass
        lines.append(line)
    for r in outcome.results:
        if r.ok and r.tx_hash and r.tx_hash != "dry-run":
            url = (
                f"{explorer_tx_url}{r.tx_hash}"
                if explorer_tx_url.endswith("/")
                else f"{explorer_tx_url.rstrip('/')}/{r.tx_hash}"
            )
            lines.append(f"🔗 {r.address[:6]}…{r.address[-4:]}: {url}")
    return "\n".join(lines)