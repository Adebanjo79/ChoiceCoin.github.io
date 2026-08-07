from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import Web3

ROOT = Path(__file__).resolve().parents[1]
SEADROP_DEFAULT = "0x00005EA00Ac477B1030CE78506496e8C2dE24bf5"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return float(raw)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return int(raw)


def parse_private_keys(raw: str) -> list[LocalAccount]:
    accounts: list[LocalAccount] = []
    seen: set[str] = set()
    for part in raw.replace("\n", ",").split(","):
        key = part.strip()
        if not key:
            continue
        if not key.startswith("0x"):
            key = "0x" + key
        account = Account.from_key(key)
        addr = account.address.lower()
        if addr in seen:
            continue
        seen.add(addr)
        accounts.append(account)
    return accounts


@dataclass(frozen=True)
class Config:
    rpc_url: str
    chain_id: int
    seadrop_address: str
    explorer_tx_url: str
    accounts: list[LocalAccount]
    opensea_api_key: str
    opensea_api_base: str
    opensea_chain: str
    telegram_bot_token: str
    telegram_chat_id: str
    poll_seconds: float
    lookback_blocks: int
    default_quantity: int
    dry_run: bool
    max_fee_gwei: float
    max_priority_fee_gwei: float
    confirmations: int

    @property
    def seadrop(self) -> str:
        return Web3.to_checksum_address(self.seadrop_address)

    @property
    def wallets(self) -> list[str]:
        return [a.address for a in self.accounts]


def load_config(env_file: str | Path | None = None) -> Config:
    load_dotenv(env_file or ROOT / ".env", override=False)
    accounts = parse_private_keys(os.getenv("PRIVATE_KEYS", ""))
    return Config(
        rpc_url=os.getenv("RPC_URL", "https://rpc.mainnet.chain.robinhood.com").strip(),
        chain_id=_env_int("CHAIN_ID", 4663),
        seadrop_address=os.getenv("SEADROP_ADDRESS", SEADROP_DEFAULT).strip(),
        explorer_tx_url=os.getenv(
            "EXPLORER_TX_URL",
            "https://robinhoodchain.blockscout.com/tx/",
        ).strip(),
        accounts=accounts,
        opensea_api_key=os.getenv("OPENSEA_API_KEY", "").strip(),
        opensea_api_base=os.getenv("OPENSEA_API_BASE", "https://api.opensea.io").rstrip("/"),
        opensea_chain=os.getenv("OPENSEA_CHAIN", "robinhood").strip(),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        poll_seconds=_env_float("POLL_SECONDS", 2.0),
        lookback_blocks=_env_int("LOOKBACK_BLOCKS", 8),
        default_quantity=_env_int("DEFAULT_QUANTITY", 0),
        dry_run=_env_bool("DRY_RUN", True),
        max_fee_gwei=_env_float("MAX_FEE_GWEI", 5.0),
        max_priority_fee_gwei=_env_float("MAX_PRIORITY_FEE_GWEI", 1.0),
        confirmations=_env_int("CONFIRMATIONS", 1),
    )