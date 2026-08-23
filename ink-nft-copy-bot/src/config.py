from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from web3 import Web3

ROOT = Path(__file__).resolve().parents[1]
SEADROP_DEFAULT = "0x00005EA00Ac477B1030CE78506496e8C2dE24bf5"
INK_CHAIN_ID = 57073


def _strip_env_paste(raw: str) -> str:
    """Strip accidental `RPC_URL=` / `KEY=` prefixes pasted into values."""
    value = (raw or "").strip().strip('"').strip("'")
    if "=" in value and re.match(r"^[A-Z0-9_]+=", value):
        value = value.split("=", 1)[1].strip().strip('"').strip("'")
    return value


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return _strip_env_paste(raw).lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return float(_strip_env_paste(str(raw)))


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return int(_strip_env_paste(str(raw)))


def _split_csv(raw: str) -> list[str]:
    out: list[str] = []
    for part in (raw or "").replace("\n", ",").split(","):
        item = _strip_env_paste(part)
        if item:
            out.append(item)
    return out


def normalize_address(addr: str) -> str:
    return Web3.to_checksum_address(_strip_env_paste(addr))


def parse_addresses(raw: str) -> list[str]:
    addrs: list[str] = []
    seen: set[str] = set()
    for item in _split_csv(raw):
        try:
            cs = normalize_address(item)
        except Exception:
            continue
        key = cs.lower()
        if key in seen:
            continue
        seen.add(key)
        addrs.append(cs)
    return addrs


@dataclass
class Config:
    telegram_bot_token: str
    telegram_owner_id: int
    chain_id: int
    rpc_urls: list[str]
    rpc_load_balance: bool
    rpc_rate_limit: float
    explorer_tx_url: str
    explorer_address_url: str
    seadrop_address: str
    target_wallets: list[str]
    private_keys_env: list[str]
    dry_run: bool
    free_mints_only: bool
    paused: bool
    poll_interval_sec: float
    catchup_chunk: int
    gas_limit: int
    max_fee_gwei: float
    max_priority_fee_gwei: float
    pending_detection: bool
    pending_ws_url: str
    mint_wallets_file: Path
    state_file: Path
    root: Path = field(default_factory=lambda: ROOT)

    @property
    def seadrop(self) -> str:
        return Web3.to_checksum_address(self.seadrop_address)


def load_config(env_file: str | Path | None = None) -> Config:
    path = Path(env_file) if env_file else ROOT / ".env"
    load_dotenv(path, override=False)

    primary = _strip_env_paste(os.getenv("RPC_URL", "https://rpc-gel.inkonchain.com"))
    extras = _split_csv(os.getenv("RPC_URLS", "https://rpc-qnd.inkonchain.com"))
    rpc_urls: list[str] = []
    for url in [primary, *extras]:
        u = _strip_env_paste(url)
        if u and u not in rpc_urls:
            rpc_urls.append(u)

    keys = _split_csv(os.getenv("PRIVATE_KEYS", ""))
    single = _strip_env_paste(os.getenv("PRIVATE_KEY", ""))
    if single:
        keys = [single, *keys]

    owner_raw = _strip_env_paste(os.getenv("TELEGRAM_OWNER_ID", "0"))
    try:
        owner_id = int(owner_raw)
    except ValueError:
        owner_id = 0

    mw = _strip_env_paste(os.getenv("MINT_WALLETS_FILE", "mint_wallets.json"))
    sf = _strip_env_paste(os.getenv("STATE_FILE", "data/state.json"))
    mint_path = Path(mw) if Path(mw).is_absolute() else ROOT / mw
    state_path = Path(sf) if Path(sf).is_absolute() else ROOT / sf

    return Config(
        telegram_bot_token=_strip_env_paste(os.getenv("TELEGRAM_BOT_TOKEN", "")),
        telegram_owner_id=owner_id,
        chain_id=_env_int("CHAIN_ID", INK_CHAIN_ID),
        rpc_urls=rpc_urls or ["https://rpc-gel.inkonchain.com"],
        rpc_load_balance=_env_bool("RPC_LOAD_BALANCE", False),
        rpc_rate_limit=_env_float("RPC_RATE_LIMIT", 25.0),
        explorer_tx_url=_strip_env_paste(
            os.getenv("EXPLORER_TX_URL", "https://explorer.inkonchain.com/tx/")
        ),
        explorer_address_url=_strip_env_paste(
            os.getenv("EXPLORER_ADDRESS_URL", "https://explorer.inkonchain.com/address/")
        ),
        seadrop_address=_strip_env_paste(os.getenv("SEADROP_ADDRESS", SEADROP_DEFAULT)),
        target_wallets=parse_addresses(os.getenv("TARGET_WALLETS", "")),
        private_keys_env=keys,
        dry_run=_env_bool("DRY_RUN", True),
        free_mints_only=_env_bool("FREE_MINTS_ONLY", True),
        paused=_env_bool("PAUSED", False),
        poll_interval_sec=_env_float("POLL_INTERVAL_SEC", 0.4),
        catchup_chunk=_env_int("CATCHUP_CHUNK", 40),
        gas_limit=_env_int("GAS_LIMIT", 350_000),
        max_fee_gwei=_env_float("MAX_FEE_GWEI", 5.0),
        max_priority_fee_gwei=_env_float("MAX_PRIORITY_FEE_GWEI", 1.0),
        pending_detection=_env_bool("PENDING_DETECTION", False),
        pending_ws_url=_strip_env_paste(
            os.getenv("PENDING_WS_URL", "wss://rpc-gel.inkonchain.com")
        ),
        mint_wallets_file=mint_path,
        state_file=state_path,
    )