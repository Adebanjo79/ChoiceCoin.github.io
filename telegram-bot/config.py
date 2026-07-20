"""Configuration helpers for the Robinhood mint-address Telegram bot."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(__file__).resolve().parent / "data"
CONFIG_PATH = DATA_DIR / "config.json"

# Robinhood Chain uses EVM addresses (0x + 40 hex chars).
EVM_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


@dataclass
class BotConfig:
    """Runtime bot settings. Persisted fields can be updated by admins."""

    mint_address: str
    token_name: str
    token_symbol: str
    explorer_url: str
    admin_ids: list[int]


def parse_admin_ids(raw: str | None) -> list[int]:
    if not raw:
        return []
    ids: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        ids.append(int(part))
    return ids


def is_valid_evm_address(address: str) -> bool:
    return bool(EVM_ADDRESS_RE.match(address.strip()))


def normalize_address(address: str) -> str:
    return address.strip()


def load_env_defaults() -> BotConfig:
    token_name = os.getenv("TOKEN_NAME", "Token").strip() or "Token"
    token_symbol = os.getenv("TOKEN_SYMBOL", "").strip()
    mint_address = normalize_address(
        os.getenv("MINT_ADDRESS", "0x0000000000000000000000000000000000000000")
    )
    explorer_url = os.getenv(
        "EXPLORER_URL", "https://robinhoodchain.blockscout.com"
    ).rstrip("/")
    return BotConfig(
        mint_address=mint_address,
        token_name=token_name,
        token_symbol=token_symbol,
        explorer_url=explorer_url,
        admin_ids=parse_admin_ids(os.getenv("ADMIN_IDS")),
    )


def load_persisted_overrides() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        with CONFIG_PATH.open(encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_persisted_overrides(config: BotConfig) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "mint_address": config.mint_address,
        "token_name": config.token_name,
        "token_symbol": config.token_symbol,
        "explorer_url": config.explorer_url,
    }
    with CONFIG_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def load_config() -> BotConfig:
    config = load_env_defaults()
    overrides = load_persisted_overrides()
    for key in ("mint_address", "token_name", "token_symbol", "explorer_url"):
        value = overrides.get(key)
        if isinstance(value, str) and value.strip():
            setattr(config, key, value.strip().rstrip("/") if key == "explorer_url" else value.strip())
    return config


def require_bot_token() -> str:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or token.startswith("123456:"):
        raise RuntimeError(
            "Set BOT_TOKEN in telegram-bot/.env (create a bot with @BotFather)."
        )
    return token


def config_snapshot(config: BotConfig) -> dict:
    return asdict(config)
