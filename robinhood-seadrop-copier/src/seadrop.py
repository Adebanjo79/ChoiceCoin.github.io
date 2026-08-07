from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from eth_abi import decode
from web3 import Web3

# SeaDrop function selectors (keccak of canonical signatures)
MINT_SIGNED = bytes.fromhex("4b61cd6f")
MINT_PUBLIC = bytes.fromhex("161ac21f")
MINT_ALLOW_LIST = bytes.fromhex("4300a4e6")
# mintAllowedTokenHolder(address,address,address,(address,uint256[]))
MINT_ALLOWED_TOKEN_HOLDER = bytes.fromhex("99eb900f")

SELECTOR_NAMES = {
    MINT_SIGNED: "mintSigned",
    MINT_PUBLIC: "mintPublic",
    MINT_ALLOW_LIST: "mintAllowList",
    MINT_ALLOWED_TOKEN_HOLDER: "mintAllowedTokenHolder",
}

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
    {
        "name": "getAllowedFeeRecipients",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "nftContract", "type": "address"}],
        "outputs": [{"name": "", "type": "address[]"}],
    },
    {
        "name": "mintPublic",
        "type": "function",
        "stateMutability": "payable",
        "inputs": [
            {"name": "nftContract", "type": "address"},
            {"name": "feeRecipient", "type": "address"},
            {"name": "minterIfNotPayer", "type": "address"},
            {"name": "quantity", "type": "uint256"},
        ],
        "outputs": [],
    },
]

MINT_PARAMS_TYPES = (
    "uint256",
    "uint256",
    "uint256",
    "uint256",
    "uint256",
    "uint256",
    "uint256",
    "bool",
)


@dataclass(frozen=True)
class MintParams:
    mint_price: int
    max_total_mintable_by_wallet: int
    start_time: int
    end_time: int
    drop_stage_index: int
    max_token_supply_for_stage: int
    fee_bps: int
    restrict_fee_recipients: bool


@dataclass(frozen=True)
class DecodedSeaDropMint:
    method: str
    nft_contract: str
    fee_recipient: str
    minter_if_not_payer: str
    quantity: int
    mint_params: MintParams | None = None
    salt: int | None = None
    signature: bytes | None = None
    proof: list[bytes] | None = None
    raw_input: str = ""

    @property
    def is_signature_bound(self) -> bool:
        return self.method in {"mintSigned", "mintAllowList", "mintAllowedTokenHolder"}


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


def _addr(value: Any) -> str:
    return Web3.to_checksum_address(value)


def decode_seadrop_input(data: str | bytes) -> DecodedSeaDropMint | None:
    if isinstance(data, str):
        raw = data[2:] if data.startswith("0x") else data
        payload = bytes.fromhex(raw)
    else:
        payload = data
    if len(payload) < 4:
        return None
    selector = payload[:4]
    method = SELECTOR_NAMES.get(selector)
    if method is None:
        return None
    body = payload[4:]

    if method == "mintSigned":
        decoded = decode(
            [
                "address",
                "address",
                "address",
                "uint256",
                f"({','.join(MINT_PARAMS_TYPES)})",
                "uint256",
                "bytes",
            ],
            body,
        )
        mp = decoded[4]
        return DecodedSeaDropMint(
            method=method,
            nft_contract=_addr(decoded[0]),
            fee_recipient=_addr(decoded[1]),
            minter_if_not_payer=_addr(decoded[2]),
            quantity=int(decoded[3]),
            mint_params=MintParams(*[int(x) if not isinstance(x, bool) else x for x in mp]),
            salt=int(decoded[5]),
            signature=bytes(decoded[6]),
            raw_input="0x" + payload.hex(),
        )

    if method == "mintPublic":
        decoded = decode(["address", "address", "address", "uint256"], body)
        return DecodedSeaDropMint(
            method=method,
            nft_contract=_addr(decoded[0]),
            fee_recipient=_addr(decoded[1]),
            minter_if_not_payer=_addr(decoded[2]),
            quantity=int(decoded[3]),
            raw_input="0x" + payload.hex(),
        )

    if method == "mintAllowList":
        decoded = decode(
            [
                "address",
                "address",
                "address",
                "uint256",
                f"({','.join(MINT_PARAMS_TYPES)})",
                "bytes32[]",
            ],
            body,
        )
        mp = decoded[4]
        return DecodedSeaDropMint(
            method=method,
            nft_contract=_addr(decoded[0]),
            fee_recipient=_addr(decoded[1]),
            minter_if_not_payer=_addr(decoded[2]),
            quantity=int(decoded[3]),
            mint_params=MintParams(*[int(x) if not isinstance(x, bool) else x for x in mp]),
            proof=[bytes(p) for p in decoded[5]],
            raw_input="0x" + payload.hex(),
        )

    # mintAllowedTokenHolder — token-gated; use OpenSea path (ids are wallet-specific)
    decoded = decode(["address", "address", "address", "(address,uint256[])"], body)
    token_ids = list(decoded[3][1])
    return DecodedSeaDropMint(
        method=method,
        nft_contract=_addr(decoded[0]),
        fee_recipient=_addr(decoded[1]),
        minter_if_not_payer=_addr(decoded[2]),
        quantity=max(1, len(token_ids)),
        raw_input="0x" + payload.hex(),
    )


def encode_mint_public(
    w3: Web3,
    nft_contract: str,
    fee_recipient: str,
    quantity: int,
    minter_if_not_payer: str = "0x0000000000000000000000000000000000000000",
) -> str:
    contract = w3.eth.contract(abi=PUBLIC_DROP_ABI)
    return contract.encode_abi(
        abi_element_identifier="mintPublic",
        args=[
            Web3.to_checksum_address(nft_contract),
            Web3.to_checksum_address(fee_recipient),
            Web3.to_checksum_address(minter_if_not_payer),
            int(quantity),
        ],
    )


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


def fetch_fee_recipients(w3: Web3, seadrop: str, nft_contract: str) -> list[str]:
    contract = w3.eth.contract(address=Web3.to_checksum_address(seadrop), abi=PUBLIC_DROP_ABI)
    recipients = contract.functions.getAllowedFeeRecipients(
        Web3.to_checksum_address(nft_contract)
    ).call()
    return [Web3.to_checksum_address(a) for a in recipients]