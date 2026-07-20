"""Telegram bot that shares a Robinhood Chain mint/contract address for one-tap copy."""

from __future__ import annotations

import logging
from html import escape

from telegram import (
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import (
    BotConfig,
    is_valid_evm_address,
    load_config,
    normalize_address,
    require_bot_token,
    save_persisted_overrides,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("robinhood-mint-bot")


def get_config(context: ContextTypes.DEFAULT_TYPE) -> BotConfig:
    return context.application.bot_data["config"]


def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if user is None:
        return False
    config = get_config(context)
    return user.id in config.admin_ids


def explorer_link(config: BotConfig) -> str:
    return f"{config.explorer_url}/address/{config.mint_address}"


def format_token_label(config: BotConfig) -> str:
    if config.token_symbol:
        return f"{config.token_name} ({config.token_symbol})"
    return config.token_name


def mint_keyboard(config: BotConfig) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="Copy mint address",
                copy_text=CopyTextButton(text=config.mint_address),
            )
        ],
        [
            InlineKeyboardButton(
                text="Open in explorer",
                url=explorer_link(config),
            )
        ],
    ]
    return InlineKeyboardMarkup(rows)


def mint_message(config: BotConfig) -> str:
    label = escape(format_token_label(config))
    address = escape(config.mint_address)
    return (
        f"<b>{label}</b> — Robinhood Chain mint address\n\n"
        f"<code>{address}</code>\n\n"
        "Tap <b>Copy mint address</b>, then paste it in Robinhood Wallet "
        "(Swap → paste contract) or your preferred Robinhood Chain trading bot."
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    config = get_config(context)
    await update.message.reply_html(
        "Welcome. I share the mint / contract address for use on "
        "<b>Robinhood Chain</b>.\n\n"
        "Commands:\n"
        "/mint — show address + copy button\n"
        "/address — same as /mint\n"
        "/help — how to use this bot\n\n"
        + mint_message(config),
        reply_markup=mint_keyboard(config),
        disable_web_page_preview=True,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    text = (
        "<b>How to use</b>\n"
        "1. Send /mint\n"
        "2. Tap <b>Copy mint address</b>\n"
        "3. Open Robinhood Wallet → Swap (or a Robinhood Chain Telegram trading bot)\n"
        "4. Paste the address and confirm it matches the explorer link\n\n"
        "<b>Admin commands</b>\n"
        "/setaddress 0x… — update the mint address\n"
        "/setname Name — update the token display name\n"
        "/setsymbol TICKER — update the ticker\n"
        "/status — show current config"
    )
    await update.message.reply_html(text)


async def mint(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    config = get_config(context)
    await update.message.reply_html(
        mint_message(config),
        reply_markup=mint_keyboard(config),
        disable_web_page_preview=True,
    )


async def set_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    if not is_admin(update, context):
        await update.message.reply_text("Only admins can update the mint address.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /setaddress 0xYourContractAddress")
        return

    address = normalize_address(context.args[0])
    if not is_valid_evm_address(address):
        await update.message.reply_text(
            "Invalid address. Robinhood Chain uses EVM addresses "
            "(0x followed by 40 hex characters)."
        )
        return

    config = get_config(context)
    config.mint_address = address
    save_persisted_overrides(config)
    logger.info("Mint address updated to %s by user %s", address, update.effective_user)
    await update.message.reply_html(
        "Mint address updated.\n\n" + mint_message(config),
        reply_markup=mint_keyboard(config),
        disable_web_page_preview=True,
    )


async def set_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    if not is_admin(update, context):
        await update.message.reply_text("Only admins can update the token name.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /setname Token Name")
        return

    config = get_config(context)
    config.token_name = " ".join(context.args).strip()
    save_persisted_overrides(config)
    await update.message.reply_text(f"Token name set to: {config.token_name}")


async def set_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    if not is_admin(update, context):
        await update.message.reply_text("Only admins can update the symbol.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /setsymbol TICKER")
        return

    config = get_config(context)
    config.token_symbol = context.args[0].strip().upper()
    save_persisted_overrides(config)
    await update.message.reply_text(f"Token symbol set to: {config.token_symbol}")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    if not is_admin(update, context):
        await update.message.reply_text("Only admins can view status.")
        return
    config = get_config(context)
    admins = ", ".join(str(i) for i in config.admin_ids) or "(none)"
    await update.message.reply_html(
        "<b>Current config</b>\n"
        f"Name: {escape(format_token_label(config))}\n"
        f"Address: <code>{escape(config.mint_address)}</code>\n"
        f"Explorer: {escape(explorer_link(config))}\n"
        f"Admins: <code>{escape(admins)}</code>",
        disable_web_page_preview=True,
    )


async def on_plain_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """If someone pastes only 'mint' / 'ca' / 'address', show the mint card."""
    if update.message is None or not update.message.text:
        return
    text = update.message.text.strip().lower()
    if text in {"mint", "ca", "address", "contract", "copy"}:
        await mint(update, context)


def build_application(token: str | None = None) -> Application:
    bot_token = token or require_bot_token()
    config = load_config()
    application = Application.builder().token(bot_token).build()
    application.bot_data["config"] = config

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler(["mint", "address", "ca"], mint))
    application.add_handler(CommandHandler("setaddress", set_address))
    application.add_handler(CommandHandler("setname", set_name))
    application.add_handler(CommandHandler("setsymbol", set_symbol))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_plain_text)
    )
    return application


def main() -> None:
    application = build_application()
    logger.info("Starting Robinhood mint-address bot (polling)")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
