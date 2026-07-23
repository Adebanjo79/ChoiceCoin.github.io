"""Telegram alert sender."""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)


class TelegramAlerter:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = bool(bot_token and chat_id)

    def send(self, text: str, parse_mode: str = "Markdown") -> bool:
        if not self.enabled:
            logger.warning("Telegram not configured — printing alert to console instead")
            print("\n" + text + "\n")
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        # Telegram Markdown can fail on special chars — fallback to plain
        for mode in (parse_mode, None):
            payload = {"chat_id": self.chat_id, "text": text[:4000]}
            if mode:
                payload["parse_mode"] = mode
            try:
                resp = requests.post(url, json=payload, timeout=20)
                if resp.ok:
                    return True
                logger.warning("Telegram send failed (%s): %s", resp.status_code, resp.text[:200])
            except Exception as exc:  # noqa: BLE001
                logger.error("Telegram error: %s", exc)
        return False
