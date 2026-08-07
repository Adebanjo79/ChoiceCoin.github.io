from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable

from eth_account.signers.local import LocalAccount
from web3 import Web3

from .chain import ChainClient, SentTx
from .opensea import OpenSeaClient, OpenSeaError
from .seadrop import (
    DecodedSeaDropMint,
    encode_mint_public,
    fetch_fee_recipients,
    fetch_public_drop,
)

logger = logging.getLogger(__name__)

ZERO = "0x0000000000000000000000000000000000000000"


@dataclass(frozen=True)
class WalletResult:
    address: str
    ok: bool
    detail: str
    tx_hash: str | None = None
    strategy: str | None = None


@dataclass(frozen=True)
class CopyResult:
    nft_contract: str
    method: str
    quantity: int
    strategy: str
    results: list[WalletResult]

    @property
    def ok_count(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if not r.ok)


class SeaDropCopier:
    """
    Copy SeaDrop mints without replaying wallet-bound signatures.

    Strategy:
      1. If public drop is active → mintPublic (no OpenSea signature needed)
      2. Else for mintSigned / allowlist stages → OpenSea Drops API builds a
         fresh mintSigned tx bound to *our* wallet
      3. Never reuse the target wallet's signature / merkle proof
    """

    def __init__(
        self,
        chain: ChainClient,
        accounts: list[LocalAccount],
        seadrop: str,
        opensea: OpenSeaClient | None,
        dry_run: bool = True,
        default_quantity: int = 0,
    ):
        self.chain = chain
        self.accounts = accounts
        self.seadrop = Web3.to_checksum_address(seadrop)
        self.opensea = opensea
        self.dry_run = dry_run
        self.default_quantity = default_quantity
        self._slug_cache: dict[str, str] = {}

    def choose_quantity(self, decoded: DecodedSeaDropMint) -> int:
        if self.default_quantity > 0:
            qty = self.default_quantity
        else:
            qty = max(1, int(decoded.quantity))
        if decoded.mint_params is not None:
            cap = int(decoded.mint_params.max_total_mintable_by_wallet)
            if cap > 0:
                qty = min(qty, cap)
        return max(1, qty)

    def resolve_slug(self, nft_contract: str) -> str:
        key = nft_contract.lower()
        if key in self._slug_cache:
            return self._slug_cache[key]
        if self.opensea is None:
            raise OpenSeaError("OPENSEA_API_KEY required to resolve collection slug")
        slug = self.opensea.collection_slug_for_contract(nft_contract)
        self._slug_cache[key] = slug
        return slug

    def plan_strategy(self, decoded: DecodedSeaDropMint) -> str:
        now = int(time.time())
        public = fetch_public_drop(self.chain.w3, self.seadrop, decoded.nft_contract)
        if public.is_active(now):
            return "mintPublic"
        if decoded.method == "mintPublic":
            # Target used public but stage may have ended — still try OpenSea
            return "opensea"
        if decoded.is_signature_bound:
            return "opensea"
        return "opensea"

    def copy_mint(self, decoded: DecodedSeaDropMint) -> CopyResult:
        if not self.accounts:
            return CopyResult(
                nft_contract=decoded.nft_contract,
                method=decoded.method,
                quantity=0,
                strategy="none",
                results=[
                    WalletResult(
                        address="n/a",
                        ok=False,
                        detail="No PRIVATE_KEYS configured",
                    )
                ],
            )

        quantity = self.choose_quantity(decoded)
        strategy = self.plan_strategy(decoded)
        logger.info(
            "Copying %s nft=%s qty=%s strategy=%s wallets=%s dry_run=%s",
            decoded.method,
            decoded.nft_contract,
            quantity,
            strategy,
            len(self.accounts),
            self.dry_run,
        )

        results: list[WalletResult] = []
        with ThreadPoolExecutor(max_workers=max(1, len(self.accounts))) as pool:
            futures = {
                pool.submit(self._mint_one, account, decoded, quantity, strategy): account
                for account in self.accounts
            }
            for fut in as_completed(futures):
                results.append(fut.result())

        results.sort(key=lambda r: r.address.lower())
        return CopyResult(
            nft_contract=decoded.nft_contract,
            method=decoded.method,
            quantity=quantity,
            strategy=strategy,
            results=results,
        )

    def _mint_one(
        self,
        account: LocalAccount,
        decoded: DecodedSeaDropMint,
        quantity: int,
        strategy: str,
    ) -> WalletResult:
        addr = account.address
        try:
            if strategy == "mintPublic":
                sent = self._mint_public(account, decoded, quantity)
                return WalletResult(
                    address=addr,
                    ok=True,
                    detail="mintPublic ok" + (" (dry-run)" if sent.dry_run else ""),
                    tx_hash=sent.hash,
                    strategy="mintPublic",
                )

            sent = self._mint_via_opensea(account, decoded, quantity)
            return WalletResult(
                address=addr,
                ok=True,
                detail="OpenSea mintSigned ok" + (" (dry-run)" if sent.dry_run else ""),
                tx_hash=sent.hash,
                strategy="opensea",
            )
        except OpenSeaError as exc:
            return WalletResult(
                address=addr,
                ok=False,
                detail=f"OpenSea: {exc}",
                strategy=strategy,
            )
        except Exception as exc:
            return WalletResult(
                address=addr,
                ok=False,
                detail=str(exc),
                strategy=strategy,
            )

    def _mint_public(
        self,
        account: LocalAccount,
        decoded: DecodedSeaDropMint,
        quantity: int,
    ) -> SentTx:
        public = fetch_public_drop(self.chain.w3, self.seadrop, decoded.nft_contract)
        fee_recipient = decoded.fee_recipient
        if fee_recipient == ZERO:
            recipients = fetch_fee_recipients(self.chain.w3, self.seadrop, decoded.nft_contract)
            if not recipients:
                raise RuntimeError("No allowed fee recipient for public mint")
            fee_recipient = recipients[0]
        data = encode_mint_public(
            self.chain.w3,
            decoded.nft_contract,
            fee_recipient,
            quantity,
        )
        value = int(public.mint_price) * int(quantity)
        return self.chain.send_contract_tx(
            account,
            self.seadrop,
            data,
            value=value,
            dry_run=self.dry_run,
        )

    def _mint_via_opensea(
        self,
        account: LocalAccount,
        decoded: DecodedSeaDropMint,
        quantity: int,
    ) -> SentTx:
        if self.opensea is None:
            raise OpenSeaError(
                "SeaDrop mintSigned is signature-bound — set OPENSEA_API_KEY so we can "
                "request a fresh signature for this wallet (cannot copy theirs)"
            )
        slug = self.resolve_slug(decoded.nft_contract)
        mint_tx = self.opensea.build_mint_transaction(slug, account.address, quantity)
        return self.chain.send_contract_tx(
            account,
            mint_tx.to,
            mint_tx.data,
            value=mint_tx.value,
            dry_run=self.dry_run,
        )


def format_copy_report(
    decoded: DecodedSeaDropMint,
    copy: CopyResult,
    source_tx: str,
    from_address: str,
    block_number: int,
    explorer_tx_url: str,
    value_wei: int = 0,
) -> str:
    short = lambda a: f"{a[:6]}…{a[-4:]}" if len(a) > 12 else a
    source = (
        f"{explorer_tx_url}{source_tx}"
        if explorer_tx_url.endswith("/")
        else f"{explorer_tx_url.rstrip('/')}/{source_tx}"
    )
    lines = [
        "👀 Target mint activity",
        f"From: {from_address}",
        f"Block: {block_number}",
        f"Contract: SeaDrop | NFT: {decoded.nft_contract}",
        f"SeaDrop method: {decoded.method}",
        f"Value: {value_wei / 1e18:g} ETH",
        f"Hint: NFT mint via {decoded.method}",
        f"Source: {source}",
        f"Strategy: {copy.strategy} (fresh OpenSea sig / public — never reuse theirs)",
        f"Minting wallets: {len(copy.results)} (parallel)",
        "Copying…",
        "",
        f"Done for this mint: {copy.ok_count} ok, {copy.fail_count} failed "
        f"(tried {len(copy.results)} wallets).",
        "",
    ]

    for r in copy.results:
        mark = "✅" if r.ok else "❌"
        extra = f" tx={r.tx_hash}" if r.tx_hash and r.tx_hash != "dry-run" else ""
        lines.append(f"{mark} {short(r.address)}: {r.detail}{extra}")
    return "\n".join(lines)


# Keep a tiny injectable hook for tests
CopyFn = Callable[[DecodedSeaDropMint], CopyResult]