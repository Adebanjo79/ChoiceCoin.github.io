"""Interactive Telegram command bot — full daily odds + SportyBet control."""

from __future__ import annotations

import logging
import re
from typing import Callable

from src.runtime_status import RuntimeStatus
from src.telegram_alerter import TelegramAlerter

logger = logging.getLogger(__name__)

COMMANDS = [
    {"command": "start", "description": "Welcome + menu"},
    {"command": "help", "description": "List all commands"},
    {"command": "menu", "description": "Quick command menu"},
    {"command": "status", "description": "Bot health / last scan"},
    {"command": "fixtures", "description": "Today's fixtures + dates"},
    {"command": "tips", "description": "Full board: fixtures + 3/5/50"},
    {"command": "3odd", "description": "Daily ≈3.0 odds + SportyBet code"},
    {"command": "5odd", "description": "Daily ≈5.0 odds + SportyBet code"},
    {"command": "50odd", "description": "Daily ≈50 odds + SportyBet code"},
    {"command": "codes", "description": "SportyBet booking codes only"},
    {"command": "sportybet", "description": "Same as /codes"},
    {"command": "safety", "description": "Refresh tips + codes now"},
    {"command": "refresh", "description": "Same as /safety"},
    {"command": "ping", "description": "Quick alive check"},
]

HELP_TEXT = (
    "⚽ Daily Fixture Odds Bot\n"
    "Today's matches → ≈3 / ≈5 / ≈50 odds + SportyBet codes\n"
    "─" * 28 + "\n"
    "📅 FIXTURES\n"
    "• /fixtures — today's matches + dates\n\n"
    "🎯 TIPS\n"
    "• /tips — full daily board\n"
    "• /3odd — ≈3.0 odds singles\n"
    "• /5odd — ≈5.0 odds singles\n"
    "• /50odd — ≈50 odds singles\n\n"
    "🎫 SPORTYBET\n"
    "• /codes — booking codes (easy copy)\n"
    "• /sportybet — same as /codes\n"
    "  Load: SportyBet → Betslip → Booking Code → Load\n\n"
    "🔄 REFRESH\n"
    "• /safety or /refresh — scan now\n\n"
    "📡 SYSTEM\n"
    "• /status — health / last scan\n"
    "• /ping — alive check\n"
    "• /help — this menu\n\n"
    "Not betting advice. Stake responsibly."
)


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
        on_codes: Callable[[], str] | None = None,
    ) -> None:
        self.telegram = telegram
        self.status = status
        self.allowed_chat_ids = {str(c).strip() for c in allowed_chat_ids if str(c).strip()}
        self.on_safety_refresh = on_safety_refresh
        self.on_tips = on_tips
        self.on_band = on_band
        self.on_fixtures = on_fixtures
        self.on_codes = on_codes

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
        # Long refresh: acknowledge first so the chat doesn't feel stuck
        if cmd in {"/safety", "/refresh", "/scan"}:
            self.telegram.send(
                "⏳ Refreshing today's fixtures, tips & SportyBet codes…\n"
                "This can take ~30–90 seconds.",
                chat_id=chat_id,
            )

        reply = self._dispatch(cmd)
        self.telegram.send(reply, chat_id=chat_id)

    def _dispatch(self, cmd: str) -> str:
        if cmd in {"/start", "/help", "/menu", "/commands"}:
            return HELP_TEXT
        if cmd == "/ping":
            return f"pong ✅ | uptime {self.status.uptime()} | mode {self.status.mode}"
        if cmd == "/status":
            return self.status.format_status()
        if cmd in {"/fixtures", "/fixture", "/matches"}:
            if self.on_fixtures:
                return self._or_refresh_hint(self.on_fixtures())
            return "No fixtures cached. Send /safety to scan."
        if cmd == "/tips":
            if self.on_tips:
                return self._or_refresh_hint(self.on_tips())
            return "No tips cached yet. Send /safety to scan."
        if cmd in {"/3odd", "/3", "/safety3", "/odd3"}:
            if self.on_band:
                return self._or_refresh_hint(self.on_band("3odd"))
            return "3-odd tips unavailable. Send /safety"
        if cmd in {"/5odd", "/5", "/odd5"}:
            if self.on_band:
                return self._or_refresh_hint(self.on_band("5odd"))
            return "5-odd tips unavailable. Send /safety"
        if cmd in {"/50odd", "/50", "/odd50"}:
            if self.on_band:
                return self._or_refresh_hint(self.on_band("50odd"))
            return "50-odd tips unavailable. Send /safety"
        if cmd in {"/codes", "/code", "/sportybet", "/booking", "/sb"}:
            if self.on_codes:
                return self._or_refresh_hint(self.on_codes())
            return "No SportyBet codes cached. Send /safety to refresh."
        if cmd in {"/safety", "/refresh", "/scan"}:
            if self.on_safety_refresh:
                return self.on_safety_refresh()
            return "Refresh not available in this mode. Run: python main.py --daemon"
        return (
            "Unknown command. Send /help for the full menu.\n"
            "Quick: /tips /fixtures /3odd /5odd /50odd /codes /safety /status"
        )

    @staticmethod
    def _or_refresh_hint(text: str) -> str:
        lowered = (text or "").lower()
        empty_markers = (
            "no tips yet",
            "no fixtures yet",
            "no qualifying",
            "no sportybet codes yet",
            "not cached",
        )
        if any(m in lowered for m in empty_markers):
            return (
                f"{text}\n\n"
                "Tip: send /safety to refresh today's scan + SportyBet codes."
            )
        return text

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
