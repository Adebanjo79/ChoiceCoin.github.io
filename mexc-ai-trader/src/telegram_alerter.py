"""Telegram alert sender + on-demand command listener (status / help)."""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable

import requests

logger = logging.getLogger(__name__)


def _clean_secret(value: str) -> str:
    """Strip spaces/quotes that break Telegram auth when pasted into .env."""
    return (value or "").strip().strip('"').strip("'").strip()


class TelegramAlerter:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = _clean_secret(bot_token)
        self.chat_id = _clean_secret(chat_id)
        self.enabled = bool(self.bot_token and self.chat_id)
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
        """Background thread: reply when user types status / help in Telegram."""
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
        logger.info("Telegram command listener started — type 'status' in Telegram anytime")

    @staticmethod
    def _is_status_request(text: str) -> bool:
        t = text.lower().strip()
        # Exact / short commands
        first = t.split()[0].lstrip("/") if t else ""
        if first in {"status", "stat", "s"}:
            return True
        # Natural asks: "status?", "check status", "bot status", etc.
        if re.search(r"\bstatus\b", t):
            return True
        return False

    @staticmethod
    def _is_help_request(text: str) -> bool:
        t = text.lower().strip()
        first = t.split()[0].lstrip("/") if t else ""
        return first in {"help", "start", "commands", "menu"}

    def _same_chat(self, chat_id: str) -> bool:
        return str(chat_id).strip() == self.chat_id

    def _poll_commands(self, status_fn: Callable[[], str]) -> None:
        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
        # Skip old messages so we only answer new asks
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
                    if not text or not self._same_chat(chat_id):
                        continue
                    if self._is_status_request(text):
                        logger.info("Telegram status requested by chat %s", chat_id)
                        self.send(status_fn())
                    elif self._is_help_request(text):
                        self.send(
                            "MEXC Spot bot commands:\n"
                            "• status — live scan status (manual check anytime)\n"
                            "• help — this message\n\n"
                            "Trade alerts are sent automatically when a setup is valid.\n"
                            "Keep TELEGRAM_STATUS=false to avoid scan spam."
                        )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Telegram listener loop error: %s", exc)
                time.sleep(5)
