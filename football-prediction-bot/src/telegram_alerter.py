"""Minimal Telegram alerter."""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)


class TelegramAlerter:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = (bot_token or "").strip()
        self.chat_id = (chat_id or "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send(self, text: str) -> bool:
        if not self.enabled:
            logger.info("Telegram not configured — skipping send")
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            resp = requests.post(
                url,
                json={"chat_id": self.chat_id, "text": text},
                timeout=30,
            )
            if resp.status_code != 200:
                logger.error("Telegram error: %s", resp.text[:300])
                return False
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Telegram send failed: %s", exc)
            return False
