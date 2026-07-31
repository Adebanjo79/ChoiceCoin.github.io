"""Telegram Bot API helpers (send + long-poll updates)."""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)


class TelegramAlerter:
    def __init__(self, bot_token: str, chat_id: str = "") -> None:
        self.bot_token = (bot_token or "").strip()
        self.chat_id = str(chat_id or "").strip()
        self.base = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else ""
        self._offset = 0

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    @property
    def bot_ready(self) -> bool:
        """Token present — enough to poll commands / send if chat known."""
        return bool(self.bot_token)

    def send(self, text: str, chat_id: str | None = None) -> bool:
        target = str(chat_id or self.chat_id).strip()
        if not self.bot_token or not target:
            logger.info("Telegram not configured — skipping send")
            return False
        # Telegram hard limit ~4096 chars
        chunks = [text[i : i + 3500] for i in range(0, max(len(text), 1), 3500)] or [text]
        ok = True
        for chunk in chunks:
            if not self._api(
                "sendMessage",
                {"chat_id": target, "text": chunk, "disable_web_page_preview": True},
            ):
                ok = False
        return ok

    def get_me(self) -> dict[str, Any] | None:
        return self._api("getMe")

    def set_commands(self, commands: list[dict[str, str]]) -> bool:
        return bool(self._api("setMyCommands", {"commands": commands}))

    def get_updates(self, timeout: int = 20) -> list[dict[str, Any]]:
        if not self.bot_ready:
            return []
        data = self._api(
            "getUpdates",
            {
                "offset": self._offset,
                "timeout": timeout,
                "allowed_updates": ["message"],
            },
            timeout=timeout + 10,
        )
        if not data:
            return []
        updates = data if isinstance(data, list) else []
        # _api returns result payload for getUpdates as list
        return updates

    def acknowledge(self, update_id: int) -> None:
        self._offset = update_id + 1

    def poll_updates(self, timeout: int = 20) -> list[dict[str, Any]]:
        """Fetch updates and advance offset so messages are not redelivered."""
        if not self.bot_ready:
            return []
        try:
            resp = requests.get(
                f"{self.base}/getUpdates",
                params={
                    "offset": self._offset,
                    "timeout": timeout,
                    "allowed_updates": ["message"],
                },
                timeout=timeout + 15,
            )
            payload = resp.json()
            if not payload.get("ok"):
                logger.error("getUpdates failed: %s", str(payload)[:300])
                return []
            updates = payload.get("result", [])
            for upd in updates:
                uid = int(upd.get("update_id", 0))
                if uid >= self._offset:
                    self._offset = uid + 1
            return updates
        except Exception as exc:  # noqa: BLE001
            logger.error("Telegram poll failed: %s", exc)
            return []

    def _api(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: int = 30,
    ) -> Any:
        if not self.bot_token:
            return None
        try:
            resp = requests.post(f"{self.base}/{method}", json=params or {}, timeout=timeout)
            payload = resp.json()
            if not payload.get("ok"):
                logger.error("Telegram %s error: %s", method, str(payload)[:300])
                return None
            return payload.get("result")
        except Exception as exc:  # noqa: BLE001
            logger.error("Telegram %s failed: %s", method, exc)
            return None
