"""Configuration for the ETF retirement Telegram bot."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def require_bot_token() -> str:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or token.startswith("123456:"):
        raise RuntimeError(
            "Set BOT_TOKEN in etf-retirement-bot/.env "
            "(create a bot with @BotFather on Telegram)."
        )
    return token


def load_default_currency() -> str:
    return os.getenv("DEFAULT_CURRENCY", "GBP").strip().upper() or "GBP"
