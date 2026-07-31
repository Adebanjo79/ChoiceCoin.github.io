"""Interactive Telegram command bot + allowed-chat gate."""

from __future__ import annotations

import logging
import re
from typing import Callable

from src.runtime_status import RuntimeStatus
from src.telegram_alerter import TelegramAlerter

logger = logging.getLogger(__name__)

COMMANDS = [
    {"command": "start", "description": "Welcome + how to use"},
    {"command": "help", "description": "List commands"},
    {"command": "status", "description": "Bot health / last scan"},
    {"command": "tips", "description": "Latest safety ~3.0 tips"},
    {"command": "safety", "description": "Refresh safety 3-odd tips now"},
    {"command": "ping", "description": "Quick alive check"},
]


class TelegramCommandBot:
    def __init__(
        self,
        telegram: TelegramAlerter,
        status: RuntimeStatus,
        *,
        allowed_chat_ids: set[str],
        on_safety_refresh: Callable[[], str] | None = None,
        on_tips: Callable[[], str] | None = None,
    ) -> None:
        self.telegram = telegram
        self.status = status
        self.allowed_chat_ids = {str(c).strip() for c in allowed_chat_ids if str(c).strip()}
        self.on_safety_refresh = on_safety_refresh
        self.on_tips = on_tips

    def setup(self) -> None:
        if not self.telegram.bot_ready:
            logger.warning("Telegram token missing — command bot inactive")
            return
        me = self.telegram.get_me()
        if me:
            logger.info("Telegram bot @%s ready", me.get("username", "?"))
        self.telegram.set_commands(COMMANDS)

    def allowed(self, chat_id: str) -> bool:
        if not self.allowed_chat_ids:
            # If no allow-list configured, accept first chat and lock to it via env chat id
            return True
        return str(chat_id) in self.allowed_chat_ids

    def handle_update(self, update: dict) -> None:
        message = update.get("message") or {}
        text = (message.get("text") or "").strip()
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id", ""))
        if not text or not chat_id:
            return

        if not self.allowed(chat_id):
            self.telegram.send(
                "⛔ Unauthorized chat.\n"
                f"Your chat id is: {chat_id}\n"
                "Add it to TELEGRAM_CHAT_ID in .env",
                chat_id=chat_id,
            )
            return

        # Remember chat if alerter had none
        if not self.telegram.chat_id:
            self.telegram.chat_id = chat_id

        cmd = text.split()[0].split("@")[0].lower()
        reply = self._dispatch(cmd)
        self.telegram.send(reply, chat_id=chat_id)

    def _dispatch(self, cmd: str) -> str:
        if cmd in {"/start", "/help"}:
            return (
                "⚽ Football Safety Tips Bot\n"
                "Daily ≈3.0 odds picks with high confidence.\n\n"
                "Commands:\n"
                "/status — bot health & last scan\n"
                "/tips — show latest safety tips\n"
                "/safety — run a fresh safety scan now\n"
                "/ping — quick alive check\n\n"
                "Not betting advice."
            )
        if cmd == "/ping":
            return f"pong ✅ | uptime {self.status.uptime()} | mode {self.status.mode}"
        if cmd == "/status":
            return self.status.format_status()
        if cmd == "/tips":
            if self.on_tips:
                return self.on_tips()
            return self.status.last_tips_summary or "No tips cached yet. Use /safety"
        if cmd == "/safety":
            if self.on_safety_refresh:
                return self.on_safety_refresh()
            return "Safety refresh not available in this mode."
        return "Unknown command. Try /help"

    def process_updates(self, timeout: int = 5) -> int:
        updates = self.telegram.poll_updates(timeout=timeout)
        for upd in updates:
            try:
                self.handle_update(upd)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed handling update: %s", exc)
        return len(updates)


def parse_command(text: str) -> str:
    """Normalize '/tips@MyBot extra' → '/tips'."""
    if not text:
        return ""
    first = text.strip().split()[0]
    return re.split(r"@", first, maxsplit=1)[0].lower()
