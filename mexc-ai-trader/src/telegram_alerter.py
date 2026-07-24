"""Telegram alert sender + on-demand command listener (status)."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

import requests

logger = logging.getLogger(__name__)


class TelegramAlerter:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = str(chat_id).strip() if chat_id else ""
        self.enabled = bool(bot_token and self.chat_id)
        self._offset = 0
        self._listener_started = False
        self._stop = threading.Event()

    def send(self, text: str, parse_mode: str | None = None) -> bool:
        if not self.enabled:
            logger.warning("Telegram not configured — printing alert to console instead")
            print("\n" + text + "\n")
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        modes: list[str | None] = [parse_mode, None] if parse_mode else [None]
        # Avoid Markdown parse failures on status text
        for mode in modes:
            payload: dict = {"chat_id": self.chat_id, "text": text[:4000]}
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

    def start_command_listener(self, status_fn: Callable[[], str]) -> None:
        """Background thread: reply when user types status / help."""
        if not self.enabled or self._listener_started:
            return
        self._listener_started = True
        thread = threading.Thread(
            target=self._poll_commands,
            args=(status_fn,),
            name="telegram-commands",
            daemon=True,
        )
        thread.start()
        logger.info("Telegram command listener started (type 'status' in chat)")

    def _poll_commands(self, status_fn: Callable[[], str]) -> None:
        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
        # Skip old messages
        try:
            boot = requests.get(url, params={"timeout": 0}, timeout=15)
            if boot.ok:
                for item in boot.json().get("result", []):
                    self._offset = max(self._offset, int(item.get("update_id", 0)) + 1)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Telegram bootstrap getUpdates failed: %s", exc)

        while not self._stop.is_set():
            try:
                resp = requests.get(
                    url,
                    params={"timeout": 25, "offset": self._offset},
                    timeout=35,
                )
                if not resp.ok:
                    time.sleep(3)
                    continue
                for item in resp.json().get("result", []):
                    self._offset = max(self._offset, int(item.get("update_id", 0)) + 1)
                    message = item.get("message") or item.get("edited_message") or {}
                    chat = message.get("chat") or {}
                    chat_id = str(chat.get("id", ""))
                    text = (message.get("text") or "").strip()
                    if not text or chat_id != self.chat_id:
                        continue
                    cmd = text.lower().split()[0].lstrip("/")
                    if cmd in {"status", "stat", "s"}:
                        self.send(status_fn())
                    elif cmd in {"help", "start"}:
                        self.send(
                            "Commands:\n"
                            "• status — live scan status\n"
                            "• help — this message\n\n"
                            "Trade alerts are sent automatically when a setup is valid."
                        )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Telegram listener loop error: %s", exc)
                time.sleep(5)
