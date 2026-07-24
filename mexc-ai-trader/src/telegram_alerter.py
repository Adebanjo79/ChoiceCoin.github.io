"""Telegram alert sender + on-demand command listener (status)."""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable

import requests

logger = logging.getLogger(__name__)


def _clean(value: str) -> str:
    return (value or "").strip().strip('"').strip("'")


class TelegramAlerter:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = _clean(bot_token)
        self.chat_id = _clean(str(chat_id))
        self.enabled = bool(self.bot_token and self.chat_id)
        self._offset = 0
        self._listener_started = False
        self._stop = threading.Event()
        self._base = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else ""

    def send(self, text: str, parse_mode: str | None = None) -> bool:
        if not self.enabled:
            logger.warning("Telegram not configured — printing alert to console instead")
            print("\n" + text + "\n")
            return False
        url = f"{self._base}/sendMessage"
        modes: list[str | None] = [parse_mode, None] if parse_mode else [None]
        for mode in modes:
            payload: dict = {"chat_id": self.chat_id, "text": text[:4000]}
            if mode:
                payload["parse_mode"] = mode
            try:
                resp = requests.post(url, json=payload, timeout=20)
                if resp.ok:
                    return True
                logger.warning("Telegram send failed (%s): %s", resp.status_code, resp.text[:300])
            except Exception as exc:  # noqa: BLE001
                logger.error("Telegram error: %s", exc)
        return False

    def _delete_webhook(self) -> None:
        """getUpdates fails if a webhook is set — always clear it."""
        try:
            resp = requests.get(f"{self._base}/deleteWebhook", params={"drop_pending_updates": False}, timeout=15)
            logger.info("Telegram deleteWebhook: %s", resp.text[:120])
        except Exception as exc:  # noqa: BLE001
            logger.warning("deleteWebhook failed: %s", exc)

    def start_command_listener(self, status_fn: Callable[[], str]) -> None:
        """Background thread: reply when user types status / help."""
        if not self.enabled or self._listener_started:
            return
        self._listener_started = True
        self._delete_webhook()
        thread = threading.Thread(
            target=self._poll_commands,
            args=(status_fn,),
            name="telegram-commands",
            daemon=True,
        )
        thread.start()
        logger.info(
            "Telegram command listener started | chat_id=%s | type 'status' in bot chat",
            self.chat_id,
        )

    @staticmethod
    def _normalize_cmd(text: str) -> str:
        # "/status@MyBot" or "Status" or " status "
        first = text.strip().lower().split()[0] if text.strip() else ""
        first = first.lstrip("/")
        if "@" in first:
            first = first.split("@", 1)[0]
        return first

    def _allowed_chat(self, chat_id: str) -> bool:
        return str(chat_id).strip() == self.chat_id

    def _poll_commands(self, status_fn: Callable[[], str]) -> None:
        url = f"{self._base}/getUpdates"
        # Skip backlog so we only answer new messages
        try:
            boot = requests.get(url, params={"timeout": 0, "offset": -1}, timeout=15)
            if boot.ok:
                for item in boot.json().get("result", []):
                    self._offset = max(self._offset, int(item.get("update_id", 0)) + 1)
            else:
                logger.warning("Telegram bootstrap failed: %s", boot.text[:200])
                if "webhook" in boot.text.lower() or boot.status_code == 409:
                    self._delete_webhook()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Telegram bootstrap getUpdates failed: %s", exc)

        logger.info("Telegram listener polling for commands…")
        while not self._stop.is_set():
            try:
                resp = requests.get(
                    url,
                    params={
                        "timeout": 20,
                        "offset": self._offset,
                        "allowed_updates": '["message"]',
                    },
                    timeout=35,
                )
                if not resp.ok:
                    logger.warning("getUpdates HTTP %s: %s", resp.status_code, resp.text[:200])
                    if resp.status_code == 409 or "webhook" in resp.text.lower():
                        self._delete_webhook()
                    time.sleep(3)
                    continue

                payload = resp.json()
                if not payload.get("ok", True):
                    logger.warning("getUpdates not ok: %s", str(payload)[:200])
                    time.sleep(3)
                    continue

                for item in payload.get("result", []):
                    self._offset = max(self._offset, int(item.get("update_id", 0)) + 1)
                    message = item.get("message") or item.get("edited_message") or {}
                    chat = message.get("chat") or {}
                    chat_id = str(chat.get("id", "")).strip()
                    text = (message.get("text") or "").strip()
                    if not text:
                        continue

                    logger.info("Telegram message from chat_id=%s text=%r", chat_id, text[:80])

                    if not self._allowed_chat(chat_id):
                        logger.warning(
                            "Ignoring chat_id=%s (configured TELEGRAM_CHAT_ID=%s)",
                            chat_id,
                            self.chat_id,
                        )
                        # Help user fix mismatch once
                        self.send(
                            "I received a message from a different chat.\n"
                            f"Incoming chat id: {chat_id}\n"
                            f"Configured TELEGRAM_CHAT_ID: {self.chat_id}\n"
                            "Put the incoming chat id into your .env and restart."
                        )
                        continue

                    cmd = self._normalize_cmd(text)
                    # Also allow plain sentences like "status please"
                    if cmd in {"status", "stat", "s"} or re.fullmatch(r"status\b.*", text.lower()):
                        try:
                            body = status_fn()
                        except Exception as exc:  # noqa: BLE001
                            body = f"Status error: {exc}"
                            logger.exception("status_fn failed")
                        ok = self.send(body)
                        logger.info("Status reply sent=%s", ok)
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
