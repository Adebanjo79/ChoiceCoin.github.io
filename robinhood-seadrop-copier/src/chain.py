from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from eth_account.signers.local import LocalAccount
from web3 import Web3
from web3.types import TxParams


@dataclass(frozen=True)
class SentTx:
    hash: str
    from_address: str
    to: str
    value: int
    dry_run: bool = False


class ChainClient:
    def __init__(
        self,
        rpc_url: str,
        chain_id: int,
        max_fee_gwei: float = 5.0,
        max_priority_fee_gwei: float = 1.0,
    ):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        self.chain_id = chain_id
        self.max_fee_gwei = max_fee_gwei
        self.max_priority_fee_gwei = max_priority_fee_gwei
        if not self.w3.is_connected():
            raise RuntimeError(f"Cannot connect to RPC {rpc_url}")

    def get_block_number(self) -> int:
        return int(self.w3.eth.block_number)

    def get_block_transactions(self, block_number: int) -> list[dict[str, Any]]:
        block = self.w3.eth.get_block(block_number, full_transactions=True)
        txs = []
        for tx in block["transactions"]:
            txs.append(
                {
                    "hash": tx["hash"].hex() if hasattr(tx["hash"], "hex") else Web3.to_hex(tx["hash"]),
                    "from": Web3.to_checksum_address(tx["from"]),
                    "to": Web3.to_checksum_address(tx["to"]) if tx["to"] else None,
                    "value": int(tx["value"]),
                    "input": tx["input"].hex() if hasattr(tx["input"], "hex") else Web3.to_hex(tx["input"]),
                    "blockNumber": int(tx["blockNumber"]),
                }
            )
        return txs

    def balance(self, address: str) -> int:
        return int(self.w3.eth.get_balance(Web3.to_checksum_address(address)))

    def send_contract_tx(
        self,
        account: LocalAccount,
        to: str,
        data: str,
        value: int = 0,
        dry_run: bool = True,
    ) -> SentTx:
        to_cs = Web3.to_checksum_address(to)
        nonce = self.w3.eth.get_transaction_count(account.address)
        max_fee = self.w3.to_wei(self.max_fee_gwei, "gwei")
        max_priority = self.w3.to_wei(self.max_priority_fee_gwei, "gwei")
        tx: TxParams = {
            "from": account.address,
            "to": to_cs,
            "data": data,
            "value": int(value),
            "nonce": nonce,
            "chainId": self.chain_id,
            "type": 2,
            "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": max_priority,
        }
        try:
            gas = self.w3.eth.estimate_gas(tx)
            tx["gas"] = int(gas * 1.2)
        except Exception:
            tx["gas"] = 350_000

        if dry_run:
            # eth_call validates without broadcasting
            self.w3.eth.call(
                {
                    "from": account.address,
                    "to": to_cs,
                    "data": data,
                    "value": int(value),
                }
            )
            return SentTx(
                hash="dry-run",
                from_address=account.address,
                to=to_cs,
                value=int(value),
                dry_run=True,
            )

        signed = account.sign_transaction(tx)
        raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        tx_hash = self.w3.eth.send_raw_transaction(raw)
        return SentTx(
            hash=tx_hash.hex(),
            from_address=account.address,
            to=to_cs,
            value=int(value),
            dry_run=False,
        )