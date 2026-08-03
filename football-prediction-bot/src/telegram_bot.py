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
    {"command": "fixtures", "description": "Today's fixtures with dates"},
    {"command": "tips", "description": "Daily board: fixtures + 3/5/50 odds"},
    {"command": "3odd", "description": "Daily ≈3.0 odds (with date)"},
    {"command": "5odd", "description": "Daily ≈5.0 odds (with date)"},
    {"command": "50odd", "description": "Daily ≈50 odds (with date)"},
    {"command": "safety", "description": "Refresh today's tips now"},
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
        on_fixtures: Callable[[], str] | None = None,
    ) -> None:
        self.telegram = telegram
        self.status = status
        self.allowed_chat_ids = {str(c).strip() for c in allowed_chat_ids if str(c).strip()}
        self.on_safety_refresh = on_safety_refresh
        self.on_tips = on_tips
        self.on_band = on_band
        self.on_fixtures = on_fixtures

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
                "⚽ Daily Fixture Odds Bot\n"
                "Today's matches → ≈3 / ≈5 / ≈50 odds with dates.\n\n"
                "• /fixtures — today's fixture list + dates\n"
                "• /tips — full daily board\n"
                "• /3odd — daily ≈3.0 odds\n"
                "• /5odd — daily ≈5.0 odds\n"
                "• /50odd — daily ≈50 odds\n"
                "• /safety — refresh now\n"
                "• /status — bot health\n"
                "• /ping — alive check\n\n"
                "Not betting advice."
            )
        if cmd == "/ping":
            return f"pong ✅ | uptime {self.status.uptime()} | mode {self.status.mode}"
        if cmd == "/status":
            return self.status.format_status()
        if cmd in {"/fixtures", "/fixture", "/matches"}:
            if self.on_fixtures:
                return self.on_fixtures()
            return "No fixtures cached. Use /safety"
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
            return "Refresh not available in this mode."
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
