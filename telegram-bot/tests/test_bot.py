"""Unit tests for config helpers and message formatting (no live Telegram calls)."""

from __future__ import annotations

import json
from pathlib import Path

import config as bot_config
from bot import format_token_label, mint_keyboard, mint_message


def test_is_valid_evm_address() -> None:
    assert bot_config.is_valid_evm_address(
        "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0"
    )
    assert bot_config.is_valid_evm_address(
        "0x742d35cc6634c0532925a3b844bc9e7595f0beb0"
    )
    assert not bot_config.is_valid_evm_address("742d35Cc6634C0532925a3b844Bc9e7595f0bEb0")
    assert not bot_config.is_valid_evm_address("0x123")
    assert not bot_config.is_valid_evm_address("not-an-address")


def test_parse_admin_ids() -> None:
    assert bot_config.parse_admin_ids("1, 2,3") == [1, 2, 3]
    assert bot_config.parse_admin_ids("") == []
    assert bot_config.parse_admin_ids(None) == []


def test_load_and_persist_overrides(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(bot_config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(bot_config, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setenv("MINT_ADDRESS", "0x1111111111111111111111111111111111111111")
    monkeypatch.setenv("TOKEN_NAME", "Alpha")
    monkeypatch.setenv("TOKEN_SYMBOL", "ALP")
    monkeypatch.setenv("ADMIN_IDS", "42")
    monkeypatch.setenv(
        "EXPLORER_URL", "https://robinhoodchain.blockscout.com/"
    )

    loaded = bot_config.load_config()
    assert loaded.mint_address == "0x1111111111111111111111111111111111111111"
    assert loaded.token_name == "Alpha"
    assert loaded.token_symbol == "ALP"
    assert loaded.admin_ids == [42]
    assert loaded.explorer_url == "https://robinhoodchain.blockscout.com"

    loaded.mint_address = "0x2222222222222222222222222222222222222222"
    loaded.token_name = "Beta"
    bot_config.save_persisted_overrides(loaded)

    raw = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert raw["mint_address"] == "0x2222222222222222222222222222222222222222"
    assert raw["token_name"] == "Beta"

    reloaded = bot_config.load_config()
    assert reloaded.mint_address == "0x2222222222222222222222222222222222222222"
    assert reloaded.token_name == "Beta"
    assert reloaded.token_symbol == "ALP"


def test_mint_message_and_keyboard() -> None:
    cfg = bot_config.BotConfig(
        mint_address="0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
        token_name="Choice",
        token_symbol="CHOICE",
        explorer_url="https://robinhoodchain.blockscout.com",
        admin_ids=[1],
    )
    assert format_token_label(cfg) == "Choice (CHOICE)"
    html = mint_message(cfg)
    assert "Choice (CHOICE)" in html
    assert "<code>0xabcdefabcdefabcdefabcdefabcdefabcdefabcd</code>" in html
    assert "Robinhood" in html

    keyboard = mint_keyboard(cfg)
    copy_btn = keyboard.inline_keyboard[0][0]
    assert copy_btn.text == "Copy mint address"
    assert copy_btn.copy_text is not None
    assert copy_btn.copy_text.text == cfg.mint_address

    explorer_btn = keyboard.inline_keyboard[1][0]
    assert explorer_btn.url == (
        "https://robinhoodchain.blockscout.com/address/"
        "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
    )
