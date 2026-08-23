from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from eth_abi import decode, encode
from eth_utils import keccak
from web3 import Web3

ZERO = "0x0000000000000000000000000000000000000000"

# Known SeaDrop mint selectors — skip receipt fetch for these
MINT_PUBLIC = bytes.fromhex("161ac21f")  # mintPublic(address,address,address,uint256)
MINT_SIGNED = bytes.fromhex("4b61cd6f")
MINT_ALLOW_LIST = bytes.fromhex("4300a4e6")
MINT_ALLOWED_TOKEN_HOLDER = bytes.fromhex("99eb900f")

KNOWN_MINT_SELECTORS = {
    MINT_PUBLIC: "mintPublic",
    MINT_SIGNED: "mintSigned",
    MINT_ALLOW_LIST: "mintAllowList",
    MINT_ALLOWED_TOKEN_HOLDER: "mintAllowedTokenHolder",
}

# Common revert selectors (SeaDrop / payment)
NOT_ACTIVE = bytes.fromhex("13da22f2")  # NotActive()
INCORRECT_ETH = bytes.fromhex("201c04ab")  # IncorrectPayment / IncorrectETHAmount family

PUBLIC_DROP_ABI = [
    {
        "name": "getPublicDrop",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "nftContract", "type": "address"}],
        "outputs": [
            {
                "components": [
                    {"name": "mintPrice", "type": "uint80"},
                    {"name": "startTime", "type": "uint48"},
                    {"name": "endTime", "type": "uint48"},
                    {"name": "maxTotalMintableByWallet", "type": "uint16"},
                    {"name": "feeBps", "type": "uint16"},
                    {"name": "restrictFeeRecipients", "type": "bool"},
                ],
                "type": "tuple",
            }
        ],
    },
]

ERC721_NAME_ABI = [
    {
        "name": "name",
        "type": "function",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "string"}],
    }
]


@dataclass(frozen=True)
class PublicDrop:
    mint_price: int
    start_time: int
    end_time: int
    max_total_mintable_by_wallet: int
    fee_bps: int
    restrict_fee_recipients: bool

    def is_active(self, now_ts: int) -> bool:
        if self.start_time == 0 and self.end_time == 0:
            return False
        return self.start_time <= now_ts < self.end_time


@dataclass(frozen=True)
class DecodedMint:
    method: str
    selector: bytes
    nft_contract: str
    fee_recipient: str
    minter_if_not_payer: str
    quantity: int
    mint_contract: str
    value: int
    raw_input: str
    is_seadrop: bool

    @property
    def is_signature_bound(self) -> bool:
        return self.method in {"mintSigned", "mintAllowList", "mintAllowedTokenHolder"}


def _addr(value: Any) -> str:
    return Web3.to_checksum_address(value)


def decode_mint_input(
    data: str | bytes,
    *,
    to: str,
    value: int = 0,
    seadrop: str,
) -> DecodedMint | None:
    if isinstance(data, str):
        raw = data[2:] if data.startswith(("0x", "0X")) else data
        try:
            payload = bytes.fromhex(raw)
        except ValueError:
            return None
    else:
        payload = bytes(data)
    if len(payload) < 4:
        return None
    selector = payload[:4]
    method = KNOWN_MINT_SELECTORS.get(selector)
    to_cs = _addr(to) if to else ZERO
    seadrop_cs = _addr(seadrop)
    is_seadrop = to_cs.lower() == seadrop_cs.lower()

    if method == "mintPublic" and is_seadrop:
        body = payload[4:]
        try:
            decoded = decode(["address", "address", "address", "uint256"], body)
        except Exception:
            return None
        return DecodedMint(
            method=method,
            selector=selector,
            nft_contract=_addr(decoded[0]),
            fee_recipient=_addr(decoded[1]),
            minter_if_not_payer=_addr(decoded[2]),
            quantity=int(decoded[3]),
            mint_contract=to_cs,
            value=int(value),
            raw_input="0x" + payload.hex(),
            is_seadrop=True,
        )

    if method in {"mintSigned", "mintAllowList", "mintAllowedTokenHolder"} and is_seadrop:
        # Only need nft contract (first arg) for alerts; do not attempt to copy
        nft = ZERO
        try:
            # address is first 32-byte word
            nft = _addr("0x" + payload[16:36].hex())
        except Exception:
            pass
        return DecodedMint(
            method=method,
            selector=selector,
            nft_contract=nft,
            fee_recipient=ZERO,
            minter_if_not_payer=ZERO,
            quantity=0,
            mint_contract=to_cs,
            value=int(value),
            raw_input="0x" + payload.hex(),
            is_seadrop=True,
        )

    # Non-SeaDrop: only attempt if it looks like a simple free public mint we can rewrite
    if not is_seadrop and selector and int(value) == 0:
        return DecodedMint(
            method="direct",
            selector=selector,
            nft_contract=to_cs,
            fee_recipient=ZERO,
            minter_if_not_payer=ZERO,
            quantity=1,
            mint_contract=to_cs,
            value=0,
            raw_input="0x" + payload.hex(),
            is_seadrop=False,
        )
    return None


def rewrite_mint_public(
    nft_contract: str,
    fee_recipient: str,
    quantity: int,
) -> str:
    """Build mintPublic calldata with minterIfNotPayer = 0x0 (payer receives NFT)."""
    body = encode(
        ["address", "address", "address", "uint256"],
        [
            Web3.to_checksum_address(nft_contract),
            Web3.to_checksum_address(fee_recipient),
            ZERO,
            int(quantity),
        ],
    )
    return "0x" + MINT_PUBLIC.hex() + body.hex()


def try_adapt_direct_calldata(raw_input: str, our_address: str, their_address: str) -> str | None:
    """
    If their calldata embeds their wallet once as a 32-byte word, swap to ours.
    Returns None if ambiguous / not safely adaptable.
    """
    raw = raw_input[2:] if raw_input.startswith("0x") else raw_input
    try:
        payload = bytearray.fromhex(raw)
    except ValueError:
        return None
    if len(payload) < 4 + 32:
        return None
    their = their_address.lower().replace("0x", "").zfill(40)
    ours = our_address.lower().replace("0x", "").zfill(40)
    their_word = bytes.fromhex(their.rjust(64, "0"))
    ours_word = bytes.fromhex(ours.rjust(64, "0"))
    body = payload[4:]
    count = body.count(their_word)
    if count != 1:
        return None
    body = body.replace(their_word, ours_word, 1)
    return "0x" + payload[:4].hex() + body.hex()


def fetch_public_drop(w3: Web3, seadrop: str, nft_contract: str) -> PublicDrop:
    contract = w3.eth.contract(address=Web3.to_checksum_address(seadrop), abi=PUBLIC_DROP_ABI)
    result = contract.functions.getPublicDrop(Web3.to_checksum_address(nft_contract)).call()
    return PublicDrop(
        mint_price=int(result[0]),
        start_time=int(result[1]),
        end_time=int(result[2]),
        max_total_mintable_by_wallet=int(result[3]),
        fee_bps=int(result[4]),
        restrict_fee_recipients=bool(result[5]),
    )


def fetch_collection_name(w3: Web3, nft_contract: str) -> str:
    try:
        c = w3.eth.contract(address=Web3.to_checksum_address(nft_contract), abi=ERC721_NAME_ABI)
        name = c.functions.name().call()
        return str(name) if name else nft_contract
    except Exception:
        return nft_contract


def decode_revert_reason(data: bytes | str | None) -> str:
    if not data:
        return "revert"
    if isinstance(data, str):
        raw = data[2:] if data.startswith("0x") else data
        try:
            payload = bytes.fromhex(raw)
        except ValueError:
            return data[:120]
    else:
        payload = bytes(data)
    if len(payload) >= 4:
        sel = payload[:4]
        if sel == NOT_ACTIVE:
            return "NotActive (window closed / not started)"
        if sel == INCORRECT_ETH:
            return "IncorrectETHAmount / IncorrectPayment (paid mint)"
        # Error(string)
        if sel == bytes.fromhex("08c379a0"):
            try:
                msg = decode(["string"], payload[4:])[0]
                return str(msg)
            except Exception:
                pass
    return "0x" + payload[:4].hex()


def classify_skip(decoded: DecodedMint, *, free_mints_only: bool, public: PublicDrop | None, now_ts: int) -> str | None:
    """Return skip reason or None if copyable."""
    if decoded.method == "mintSigned":
        return "Skipped: SeaDrop mintSigned (signature bound to their wallet — not copyable)"
    if decoded.method == "mintAllowList":
        return "Skipped: SeaDrop allowlist (their Merkle proof — not copyable)"
    if decoded.method == "mintAllowedTokenHolder":
        return "Skipped: SeaDrop token-gated mint (not copyable)"

    if decoded.method == "mintPublic":
        if public is None:
            return "Skipped: could not read public drop"
        if not public.is_active(now_ts):
            return "Skipped: public window closed / not started (NotActive)"
        if free_mints_only and public.mint_price > 0:
            return f"Skipped: paid mint (mintPrice={public.mint_price} wei, FREE_MINTS_ONLY)"
        if free_mints_only and decoded.value > 0:
            return "Skipped: paid mint (tx value > 0, FREE_MINTS_ONLY)"
        if public.max_total_mintable_by_wallet == 0:
            return "Skipped: per-wallet cap is 0 / sold out stage"
        return None

    if decoded.method == "direct":
        if free_mints_only and decoded.value > 0:
            return "Skipped: paid direct mint (FREE_MINTS_ONLY)"
        return None

    return "Skipped: unknown mint type"


# Ensure selector constants match keccak (sanity for tests)
assert MINT_PUBLIC == keccak(text="mintPublic(address,address,address,uint256)")[:4]