from __future__ import annotations

from src.seadrop import PublicDrop, decode_seadrop_input

# Real VIBE LINGS mintSigned from
# https://robinhoodchain.blockscout.com/tx/0x6a584582bad838572b2da6482dc19c37a746609fb684573686be7fb3ac834551
MINT_SIGNED_INPUT = (
    "0x4b61cd6f"
    "00000000000000000000000084d8fba1f41156fae5147f2563d52ef7b31b899d"
    "0000000000000000000000000000a26b00c1f0df003000390027140000faa719"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000002"
    "0000000000000000000000000000000000000000000000000000000000000000"
    "0000000000000000000000000000000000000000000000000000000000000002"
    "000000000000000000000000000000000000000000000000000000006a75d928"
    "000000000000000000000000000000000000000000000000000000006a760358"
    "0000000000000000000000000000000000000000000000000000000000000002"
    "0000000000000000000000000000000000000000000000000000000000002710"
    "00000000000000000000000000000000000000000000000000000000000003e8"
    "0000000000000000000000000000000000000000000000000000000000000001"
    "a5cbe88f7186cd011667eb6f271ac5ffd2e50d74ba2ca2ac6e53918af4538ba8"
    "00000000000000000000000000000000000000000000000000000000000001c0"
    "0000000000000000000000000000000000000000000000000000000000000041"
    "d3b67afb647ea0382e6c126ae825fc9e5f2e92ec3de725a481a6ece1c490e942"
    "2391ae66aa4d6c6b575c535ac7659e51639ce81cd4bd3df434fc0b3e02acbe98"
    "1b00000000000000000000000000000000000000000000000000000000000000"
)


def test_decode_mint_signed_vibelines():
    decoded = decode_seadrop_input(MINT_SIGNED_INPUT)
    assert decoded is not None
    assert decoded.method == "mintSigned"
    assert decoded.is_signature_bound is True
    assert decoded.nft_contract.lower() == "0x84d8fba1f41156fae5147f2563d52ef7b31b899d"
    assert decoded.fee_recipient.lower() == "0x0000a26b00c1f0df003000390027140000faa719"
    assert decoded.quantity == 2
    assert decoded.mint_params is not None
    assert decoded.mint_params.mint_price == 0
    assert decoded.mint_params.max_total_mintable_by_wallet == 2
    assert decoded.mint_params.start_time == 0x6A75D928
    assert decoded.mint_params.end_time == 0x6A760358
    assert decoded.signature is not None
    assert len(decoded.signature) == 65


def test_decode_mint_public():
    # mintPublic(nft, feeRecipient, minterIfNotPayer, quantity=1)
    from eth_abi import encode

    body = encode(
        ["address", "address", "address", "uint256"],
        [
            "0x84d8FbA1F41156FAE5147f2563D52Ef7b31b899d",
            "0x0000a26b00c1F0DF003000390027140000fAa719",
            "0x0000000000000000000000000000000000000000",
            1,
        ],
    )
    data = "0x161ac21f" + body.hex()
    decoded = decode_seadrop_input(data)
    assert decoded is not None
    assert decoded.method == "mintPublic"
    assert decoded.is_signature_bound is False
    assert decoded.quantity == 1


def test_public_drop_active_window():
    drop = PublicDrop(
        mint_price=10**15,
        start_time=100,
        end_time=200,
        max_total_mintable_by_wallet=2,
        fee_bps=1000,
        restrict_fee_recipients=True,
    )
    assert drop.is_active(100) is True
    assert drop.is_active(199) is True
    assert drop.is_active(200) is False
    assert drop.is_active(99) is False


def test_unknown_selector_returns_none():
    assert decode_seadrop_input("0xdeadbeef" + "00" * 32) is None