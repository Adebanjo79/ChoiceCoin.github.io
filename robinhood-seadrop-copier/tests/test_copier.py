from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

from eth_account import Account

from src.copier import SeaDropCopier, WalletResult, format_copy_report
from src.opensea import OpenSeaError, OpenSeaMintTx
from src.seadrop import DecodedSeaDropMint, MintParams, PublicDrop
from tests.test_seadrop import MINT_SIGNED_INPUT
from src.seadrop import decode_seadrop_input


@dataclass
class FakeSent:
    hash: str
    from_address: str
    to: str
    value: int
    dry_run: bool = True


def _account():
    return Account.create()


def test_choose_quantity_clamps_to_stage_max():
    decoded = decode_seadrop_input(MINT_SIGNED_INPUT)
    assert decoded is not None
    chain = MagicMock()
    copier = SeaDropCopier(chain, [], "0x00005EA00Ac477B1030CE78506496e8C2dE24bf5", None)
    assert copier.choose_quantity(decoded) == 2
    copier = SeaDropCopier(
        chain, [], "0x00005EA00Ac477B1030CE78506496e8C2dE24bf5", None, default_quantity=9
    )
    assert copier.choose_quantity(decoded) == 2  # clamped by mintParams


def test_plan_strategy_prefers_public_when_active(monkeypatch):
    decoded = decode_seadrop_input(MINT_SIGNED_INPUT)
    assert decoded is not None
    chain = MagicMock()
    copier = SeaDropCopier(chain, [], "0x00005EA00Ac477B1030CE78506496e8C2dE24bf5", None)

    monkeypatch.setattr(
        "src.copier.fetch_public_drop",
        lambda *a, **k: PublicDrop(0, 1, 9_999_999_999, 2, 1000, True),
    )
    monkeypatch.setattr("src.copier.time.time", lambda: 1_000)
    assert copier.plan_strategy(decoded) == "mintPublic"

    monkeypatch.setattr(
        "src.copier.fetch_public_drop",
        lambda *a, **k: PublicDrop(0, 9_999_999_999, 9_999_999_999 + 10, 2, 1000, True),
    )
    assert copier.plan_strategy(decoded) == "opensea"


def test_copy_mint_uses_opensea_not_their_signature(monkeypatch):
    decoded = decode_seadrop_input(MINT_SIGNED_INPUT)
    assert decoded is not None
    account = _account()
    chain = MagicMock()
    chain.w3 = MagicMock()
    opensea = MagicMock()
    opensea.collection_slug_for_contract.return_value = "vibelings"
    opensea.build_mint_transaction.return_value = OpenSeaMintTx(
        to="0x00005EA00Ac477B1030CE78506496e8C2dE24bf5",
        data="0x4b61cd6f" + "00" * 32,
        value=0,
        chain="robinhood",
        raw={},
    )
    chain.send_contract_tx.return_value = FakeSent(
        hash="0xabc", from_address=account.address, to="0x00005EA00Ac477B1030CE78506496e8C2dE24bf5", value=0
    )

    monkeypatch.setattr(
        "src.copier.fetch_public_drop",
        lambda *a, **k: PublicDrop(0, 0, 0, 0, 0, False),
    )

    copier = SeaDropCopier(
        chain,
        [account],
        "0x00005EA00Ac477B1030CE78506496e8C2dE24bf5",
        opensea,
        dry_run=True,
    )
    result = copier.copy_mint(decoded)
    assert result.strategy == "opensea"
    assert result.ok_count == 1
    opensea.build_mint_transaction.assert_called_once_with("vibelings", account.address, 2)
    # Ensure we did not pass the target signature through
    sent_kwargs = chain.send_contract_tx.call_args
    assert sent_kwargs is not None
    data_arg = sent_kwargs.args[2] if len(sent_kwargs.args) > 2 else sent_kwargs.kwargs.get("data")
    assert data_arg.startswith("0x4b61cd6f")
    assert decoded.signature.hex() not in data_arg


def test_opensea_eligibility_error_is_reported(monkeypatch):
    decoded = decode_seadrop_input(MINT_SIGNED_INPUT)
    assert decoded is not None
    account = _account()
    chain = MagicMock()
    chain.w3 = MagicMock()
    opensea = MagicMock()
    opensea.collection_slug_for_contract.return_value = "vibelings"
    opensea.build_mint_transaction.side_effect = OpenSeaError("Not eligible for this stage")

    monkeypatch.setattr(
        "src.copier.fetch_public_drop",
        lambda *a, **k: PublicDrop(0, 0, 0, 0, 0, False),
    )

    copier = SeaDropCopier(
        chain,
        [account],
        "0x00005EA00Ac477B1030CE78506496e8C2dE24bf5",
        opensea,
        dry_run=True,
    )
    result = copier.copy_mint(decoded)
    assert result.ok_count == 0
    assert "Not eligible" in result.results[0].detail


def test_format_report_mentions_strategy():
    decoded = DecodedSeaDropMint(
        method="mintSigned",
        nft_contract="0x84d8FbA1F41156FAE5147f2563D52Ef7b31b899d",
        fee_recipient="0x0000a26b00c1F0DF003000390027140000fAa719",
        minter_if_not_payer="0x0000000000000000000000000000000000000000",
        quantity=2,
        mint_params=MintParams(0, 2, 1, 2, 2, 10000, 1000, True),
    )
    from src.copier import CopyResult

    copy = CopyResult(
        nft_contract=decoded.nft_contract,
        method="mintSigned",
        quantity=2,
        strategy="opensea",
        results=[
            WalletResult(
                address="0x545C00000000000000000000000000000000D4A5",
                ok=False,
                detail="OpenSea: Not eligible for this stage",
                strategy="opensea",
            )
        ],
    )
    text = format_copy_report(
        decoded,
        copy,
        source_tx="0x6a58",
        from_address="0xA0c9EA7Dcd2a50FC7aD758B96356e99f04b9861d",
        block_number=30285581,
        explorer_tx_url="https://robinhoodchain.blockscout.com/tx/",
    )
    assert "Strategy: opensea" in text
    assert "never reuse theirs" in text
    assert "Not eligible" in text
    assert "Skipped: SeaDrop mintSigned" not in text