"""Telegram bot: source simple long-term retirement ETFs for monthly £ investing."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config import require_bot_token
from etfs import get_etf
from planner import (
    build_plan_summary,
    crash_and_return_reality_check,
    parse_plan_args,
)
from recommendations import (
    DISCLAIMER,
    build_compare,
    build_etf_list,
    build_help,
    build_isa_guide,
    build_recommendation,
    format_etf_card,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("etf-retirement-bot")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    text = (
        "<b>ETF Retirement Bot</b>\n\n"
        "I help you pick a simple, diversified ETF plan for "
        "<b>£100/month</b> (or any amount) aimed at long-term retirement.\n\n"
        "<b>Straight answer up front</b>\n"
        "• No ETF can promise <b>15% every year</b>\n"
        "• No stock ETF is <b>crash-proof</b>\n"
        "• The durable approach is a low-cost global accumulating ETF "
        "(default pick: <b>VWRP</b>) bought monthly inside an ISA\n\n"
        "Try /recommend or /help"
    )
    await update.message.reply_html(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_html(build_help())


async def recommend(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    args = context.args or []
    monthly = 100.0
    years = 30
    risk = "balanced"
    try:
        if len(args) >= 1:
            monthly = float(args[0])
        if len(args) >= 2:
            years = int(float(args[1]))
        if len(args) >= 3:
            risk = args[2].lower()
        if monthly <= 0 or years < 1 or years > 60:
            raise ValueError("bad range")
        if risk not in {"balanced", "growth", "calm", "conservative", "aggressive", "low", "high"}:
            risk = "balanced"
    except ValueError:
        await update.message.reply_text(
            "Usage: /recommend [monthly_gbp] [years] [balanced|growth|calm]\n"
            "Example: /recommend 100 30 balanced"
        )
        return

    await update.message.reply_html(
        build_recommendation(monthly, years, risk),
        disable_web_page_preview=True,
    )


async def plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    try:
        monthly, years, rate = parse_plan_args(context.args or [])
    except ValueError as exc:
        await update.message.reply_text(
            f"{exc}\nUsage: /plan [monthly] [years] [return%]\n"
            "Example: /plan 100 30 8"
        )
        return

    await update.message.reply_html(build_plan_summary(monthly, years, rate))


async def etfs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_html(build_etf_list(), disable_web_page_preview=True)


async def etf_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    if not context.args:
        await update.message.reply_text("Usage: /etf VWRP")
        return
    etf = get_etf(context.args[0])
    if etf is None:
        await update.message.reply_text(
            f"Unknown ticker {context.args[0]!r}. Try /etfs"
        )
        return
    await update.message.reply_html(
        format_etf_card(etf) + "\n\n" + DISCLAIMER,
        disable_web_page_preview=True,
    )


async def compare(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Usage: /compare VWRP VUAG [SWDA …]")
        return
    await update.message.reply_html(
        build_compare(context.args),
        disable_web_page_preview=True,
    )


async def reality(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_html(crash_and_return_reality_check())


async def isa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_html(build_isa_guide())


def build_app(token: str) -> Application:
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("recommend", recommend))
    app.add_handler(CommandHandler("plan", plan))
    app.add_handler(CommandHandler("etfs", etfs_command))
    app.add_handler(CommandHandler("etf", etf_detail))
    app.add_handler(CommandHandler("compare", compare))
    app.add_handler(CommandHandler("reality", reality))
    app.add_handler(CommandHandler("isa", isa))
    return app


def main() -> None:
    token = require_bot_token()
    app = build_app(token)
    logger.info("ETF retirement bot starting (long polling)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
