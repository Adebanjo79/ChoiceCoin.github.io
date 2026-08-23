from __future__ import annotations

from eth_abi import encode
from eth_utils import keccak

from src.config import _strip_env_paste, parse_addresses
from src.copy_engine import collapse_identical_skips, WalletOutcome
from src.seadrop import (
    MINT_PUBLIC,
    PublicDrop,
    classify_skip,
    decode_mint_input,
    rewrite_mint_public,
    try_adapt_direct_calldata,
)


SEADROP = "0x00005EA00Ac477B1030CE78506496e8C2dE24bf5"
NFT = "0x1111111111111111111111111111111111111111"
FEE = "0x0000a26b00c1F0DF003000390027140000fAa719"


def test_strip_env_paste():
    assert _strip_env_paste("RPC_URL=https://rpc-gel.inkonchain.com") == "https://rpc-gel.inkonchain.com"
    assert _strip_env_paste("https://rpc-gel.inkonchain.com") == "https://rpc-gel.inkonchain.com"


def test_mint_public_selector():
    assert MINT_PUBLIC == keccak(text="mintPublic(address,address,address,uint256)")[:4]
    assert MINT_PUBLIC.hex() == "161ac21f"


def test_decode_and_rewrite_mint_public():
    body = encode(["address", "address", "address", "uint256"], [NFT, FEE, NFT, 2])
    raw = "0x" + MINT_PUBLIC.hex() + body.hex()
    decoded = decode_mint_input(raw, to=SEADROP, value=0, seadrop=SEADROP)
    assert decoded is not None
    assert decoded.method == "mintPublic"
    assert decoded.nft_contract.lower() == NFT.lower()
    assert decoded.quantity == 2
    rewritten = rewrite_mint_public(NFT, FEE, 2)
    # minterIfNotPayer must be zero
    assert "0000000000000000000000000000000000000000" in rewritten[2 + 8 + 64 + 64 : 2 + 8 + 64 + 64 + 64]


def test_skip_signed_and_paid():
    signed = decode_mint_input(
        "0x4b61cd6f" + "00" * 32,
        to=SEADROP,
        value=0,
        seadrop=SEADROP,
    )
    assert signed is not None
    assert classify_skip(
        signed,
        free_mints_only=True,
        public=None,
        now_ts=100,
    ).startswith("Skipped: SeaDrop mintSigned")

    body = encode(["address", "address", "address", "uint256"], [NFT, FEE, "0x" + "0" * 40, 1])
    pub_raw = "0x" + MINT_PUBLIC.hex() + body.hex()
    pub = decode_mint_input(pub_raw, to=SEADROP, value=0, seadrop=SEADROP)
    assert pub is not None
    closed = PublicDrop(0, 1000, 2000, 2, 1000, True)
    assert "NotActive" in (
        classify_skip(pub, free_mints_only=True, public=closed, now_ts=50) or ""
    )
    paid = PublicDrop(10**15, 1, 9_999_999_999, 2, 1000, True)
    assert "paid mint" in (
        classify_skip(pub, free_mints_only=True, public=paid, now_ts=100) or ""
    ).lower()
    free = PublicDrop(0, 1, 9_999_999_999, 2, 1000, True)
    assert classify_skip(pub, free_mints_only=True, public=free, now_ts=100) is None


def test_adapt_direct_calldata():
    their = "0x2222222222222222222222222222222222222222"
    ours = "0x3333333333333333333333333333333333333333"
    # fake selector + one address word
    word = their.lower().replace("0x", "").rjust(64, "0")
    raw = "0xdeadbeef" + word + ("00" * 32)
    adapted = try_adapt_direct_calldata(raw, ours, their)
    assert adapted is not None
    assert ours.lower().replace("0x", "") in adapted.lower()
    assert their.lower().replace("0x", "") not in adapted.lower()
    # ambiguous (two occurrences) → None
    raw2 = "0xdeadbeef" + word + word
    assert try_adapt_direct_calldata(raw2, ours, their) is None


def test_collapse_identical_skips():
    results = [
        WalletOutcome("0x1111111111111111111111111111111111111111", False, "Skipped: paid"),
        WalletOutcome("0x2222222222222222222222222222222222222222", False, "Skipped: paid"),
    ]
    lines = collapse_identical_skips(results)
    assert len(lines) == 1
    assert "all 2 wallets" in lines[0]


def test_parse_addresses():
    addrs = parse_addresses(
        "0x1111111111111111111111111111111111111111,0x1111111111111111111111111111111111111111"
    )
    assert len(addrs) == 1