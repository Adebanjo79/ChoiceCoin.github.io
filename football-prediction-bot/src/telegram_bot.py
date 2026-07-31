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
    {"command": "tips", "description": "Full board: 3 / 5 / 50 odds"},
    {"command": "3odd", "description": "Best ≈3.0 odds tips"},
    {"command": "5odd", "description": "Best ≈5.0 odds tips"},
    {"command": "50odd", "description": "Best ≈50 odds longshots"},
    {"command": "safety", "description": "Refresh all bands now"},
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
        on_band: Callable[[str], str] | None = None,
    ) -> None:
        self.telegram = telegram
        self.status = status
        self.allowed_chat_ids = {str(c).strip() for c in allowed_chat_ids if str(c).strip()}
        self.on_safety_refresh = on_safety_refresh
        self.on_tips = on_tips
        self.on_band = on_band

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

        if not self.telegram.chat_id:
            self.telegram.chat_id = chat_id

        cmd = parse_command(text)
        reply = self._dispatch(cmd)
        self.telegram.send(reply, chat_id=chat_id)

    def _dispatch(self, cmd: str) -> str:
        if cmd in {"/start", "/help"}:
            return (
                "⚽ Football Odds Bot\n"
                "Best sourced tips for ≈3 / ≈5 / ≈50 odds with confidence.\n\n"
                "Commands:\n"
                "/tips — full daily board\n"
                "/3odd — best ≈3.0 safety tips\n"
                "/5odd — best ≈5.0 value tips\n"
                "/50odd — best ≈50 longshots (correct scores)\n"
                "/safety — refresh scan now\n"
                "/status — bot health\n"
                "/ping — alive check\n\n"
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
        if cmd in {"/3odd", "/3", "/safety3"}:
            if self.on_band:
                return self.on_band("3odd")
            return "3-odd tips unavailable."
        if cmd in {"/5odd", "/5"}:
            if self.on_band:
                return self.on_band("5odd")
            return "5-odd tips unavailable."
        if cmd in {"/50odd", "/50"}:
            if self.on_band:
                return self.on_band("50odd")
            return "50-odd tips unavailable."
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
    if not text:
        return ""
    first = text.strip().split()[0]
    return re.split(r"@", first, maxsplit=1)[0].lower()
