from __future__ import annotations

import logging
import subprocess
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from . import HONEST_LIMITS, __version__
from .rpc import WalletStore

if TYPE_CHECKING:
    from .config import Config
    from .copy_engine import CopyEngine
    from .rpc import RpcPool
    from .watcher import MintWatcher

logger = logging.getLogger(__name__)


def git_sha(root) -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(root),
            stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except Exception:
        return "unknown"


class TelegramApp:
    def __init__(
        self,
        config: "Config",
        rpc: "RpcPool",
        wallets: WalletStore,
        engine: "CopyEngine",
        watcher: "MintWatcher",
    ):
        self.config = config
        self.rpc = rpc
        self.wallets = wallets
        self.engine = engine
        self.watcher = watcher
        self._paused = config.paused
        self._app: Application | None = None
        self._loop = None
        self.build_sha = git_sha(config.root)

    @property
    def paused(self) -> bool:
        return self._paused

    def is_owner(self, update: Update) -> bool:
        user = update.effective_user
        if not user or not self.config.telegram_owner_id:
            return False
        return user.id == self.config.telegram_owner_id

    async def _deny(self, update: Update) -> None:
        if update.message:
            if not self.config.telegram_owner_id:
                await update.message.reply_text(
                    "TELEGRAM_OWNER_ID not set. Send /start to see your user id, "
                    "then put it in .env and restart."
                )
            else:
                await update.message.reply_text("Owner only.")

    def send_alert(self, text: str) -> None:
        """Thread-safe alert from watcher / RPC threads."""
        if not self.config.telegram_owner_id:
            logger.info("ALERT (no TELEGRAM_OWNER_ID):\n%s", text)
            return
        if not self._app or self._loop is None:
            logger.info("ALERT (no telegram yet):\n%s", text)
            return
        try:
            import asyncio

            asyncio.run_coroutine_threadsafe(self._send(text), self._loop)
        except Exception:
            logger.exception("schedule alert failed")
            logger.info("ALERT:\n%s", text)

    async def _send(self, text: str) -> None:
        assert self._app is not None
        if not self.config.telegram_owner_id:
            return
        await self._app.bot.send_message(
            chat_id=self.config.telegram_owner_id,
            text=text[:4000],
            disable_web_page_preview=False,
        )

    def online_message(self) -> str:
        cfg = self.config
        lines = [
            "✅ Ethbot → Ink Chain NFT copy-mint online",
            f"Bot: @Adelaxethbot",
            f"Mode: {'DRY_RUN' if cfg.dry_run else 'LIVE'}"
            + (" | PAUSED" if self._paused else ""),
            f"Build: {self.build_sha} | v{__version__}",
            f"Chain: Ink ({cfg.chain_id})",
            f"Targets: {len(self.watcher.targets)}",
            f"Mint wallets: {len(self.wallets.all())}",
            f"RPC endpoints: {len(cfg.rpc_urls)} ({self.rpc.status_line()})",
            f"FREE_MINTS_ONLY: {cfg.free_mints_only}",
            f"PENDING_DETECTION: {cfg.pending_detection}",
            f"Owner ID: {cfg.telegram_owner_id or 'NOT SET'}",
            "",
            "Honest limits:",
            *[f"• {x}" for x in HONEST_LIMITS],
        ]
        return "\n".join(lines)

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user is None or update.message is None:
            return
        if not self.config.telegram_owner_id:
            await update.message.reply_text(
                "Ink Chain NFT copy-bot is running, but TELEGRAM_OWNER_ID is not set yet.\n\n"
                f"Your Telegram user id is: {user.id}\n\n"
                f"Set TELEGRAM_OWNER_ID={user.id} in .env (or secrets), restart the bot, "
                "then send /status.\n\n"
                "Also set TARGET_WALLETS and PRIVATE_KEYS. Keep DRY_RUN=true until tests look good."
            )
            return
        if not self.is_owner(update):
            return await self._deny(update)
        await update.message.reply_text(self.online_message())

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_owner(update):
            return await self._deny(update)
        text = "\n".join(
            [
                "Commands (owner only):",
                "/status — mode, build, targets, wallets, RPC",
                "/targets — list watched wallets",
                "/wallets — list minting wallets",
                "/addwallet <private_key> [label] — add mint key → mint_wallets.json",
                "/removewallet <address> — remove Telegram-added key",
                "/pause — stop copying (still watch)",
                "/resume — resume copying",
                "/balance — ETH balances for mint wallets",
                "/help — this message",
                "",
                "Copies only free SeaDrop mintPublic (price=0, window open).",
                "Skips mintSigned / allowlist / paid / closed / sold-out.",
                "",
                "Honest limits:",
                *[f"• {x}" for x in HONEST_LIMITS],
            ]
        )
        await update.message.reply_text(text)

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_owner(update):
            return await self._deny(update)
        try:
            tip = self.rpc.block_number()
        except Exception as exc:
            tip = f"error: {exc}"
        msg = self.online_message() + f"\nTip block: {tip}\nCursor: {self.watcher._cursor}"
        await update.message.reply_text(msg)

    async def cmd_targets(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_owner(update):
            return await self._deny(update)
        ts = self.watcher.targets
        if not ts:
            await update.message.reply_text("No targets. Set TARGET_WALLETS in .env.")
            return
        await update.message.reply_text("Targets:\n" + "\n".join(f"• `{t}`" for t in ts))

    async def cmd_wallets(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_owner(update):
            return await self._deny(update)
        ws = self.wallets.all()
        if not ws:
            await update.message.reply_text("No mint wallets. Set PRIVATE_KEYS or /addwallet.")
            return
        lines = [f"• {w.address} ({w.source}" + (f", {w.label}" if w.label else "") + ")" for w in ws]
        await update.message.reply_text("Mint wallets:\n" + "\n".join(lines))

    async def cmd_addwallet(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_owner(update):
            return await self._deny(update)
        if not context.args:
            await update.message.reply_text("Usage: /addwallet <private_key> [label]")
            return
        key = context.args[0]
        label = " ".join(context.args[1:]) if len(context.args) > 1 else ""
        try:
            w = self.wallets.add(key, label=label)
            # delete message with key if possible
            try:
                await update.message.delete()
            except Exception:
                pass
            await context.bot.send_message(
                chat_id=self.config.telegram_owner_id,
                text=f"Added mint wallet {w.address}" + (f" ({label})" if label else ""),
            )
        except Exception as exc:
            await update.message.reply_text(f"Failed: {exc}")

    async def cmd_removewallet(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_owner(update):
            return await self._deny(update)
        if not context.args:
            await update.message.reply_text("Usage: /removewallet <address>")
            return
        try:
            ok = self.wallets.remove(context.args[0])
            await update.message.reply_text("Removed." if ok else "Not found in mint_wallets.json.")
        except Exception as exc:
            await update.message.reply_text(f"Failed: {exc}")

    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_owner(update):
            return await self._deny(update)
        self._paused = True
        await update.message.reply_text("⏸ Paused — watching only, not copying.")

    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_owner(update):
            return await self._deny(update)
        self._paused = False
        await update.message.reply_text("▶️ Resumed copying.")

    async def cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.is_owner(update):
            return await self._deny(update)
        lines = []
        for w in self.wallets.all():
            try:
                bal = self.rpc.get_balance(w.address)
                lines.append(f"{w.address}: {bal / 1e18:.6f} ETH")
            except Exception as exc:
                lines.append(f"{w.address}: error {exc}")
        await update.message.reply_text("Balances:\n" + ("\n".join(lines) if lines else "No wallets."))

    def build_application(self) -> Application:
        if not self.config.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN required")
        app = Application.builder().token(self.config.telegram_bot_token).build()
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_help))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("targets", self.cmd_targets))
        app.add_handler(CommandHandler("wallets", self.cmd_wallets))
        app.add_handler(CommandHandler("addwallet", self.cmd_addwallet))
        app.add_handler(CommandHandler("removewallet", self.cmd_removewallet))
        app.add_handler(CommandHandler("pause", self.cmd_pause))
        app.add_handler(CommandHandler("resume", self.cmd_resume))
        app.add_handler(CommandHandler("balance", self.cmd_balance))
        self._app = app
        return app


async def bind_loop(tg: TelegramApp, application: Application) -> None:
    import asyncio

    tg._loop = asyncio.get_running_loop()
    if tg.config.telegram_owner_id:
        await tg._send(tg.online_message())
    else:
        logger.warning(
            "TELEGRAM_OWNER_ID not set — message the bot with /start to learn your user id"
        )