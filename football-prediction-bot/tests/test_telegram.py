"""Tests for safety tip selection and Telegram command helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from src.models import Fixture, MarketPrediction, Tip
from src.runtime_status import RuntimeStatus
from src.selector import select_safety_tips
from src.telegram_bot import TelegramCommandBot, parse_command
from src.telegram_alerter import TelegramAlerter


def _tip(fid: str, league: str, market: str, odds: float, conf: float) -> Tip:
    return Tip(
        Fixture(
            id=fid,
            league_code=league,
            league_name=league,
            kickoff=datetime.now(timezone.utc),
            home_team=f"H{fid}",
            away_team=f"A{fid}",
        ),
        MarketPrediction(
            market=market,
            market_label=market,
            probability=1 / odds,
            fair_odds=odds,
            book_odds=odds,
            confidence=conf,
            edge=0.05,
        ),
    )


def test_select_safety_tips_limits_to_three_and_high_confidence():
    tips = [
        _tip("1", "PL", "draw", 3.0, 80),
        _tip("2", "PD", "away_or_draw", 2.9, 78),
        _tip("3", "BL1", "away_win", 3.1, 76),
        _tip("4", "FL1", "over_25", 2.8, 77),
        _tip("5", "SA", "draw", 3.0, 60),  # below safety threshold
        _tip("6", "PL", "draw", 1.5, 90),  # odds too low
    ]
    selected = select_safety_tips(
        tips,
        min_confidence=75,
        target_odds=3.0,
        odds_tolerance=0.75,
        max_tips=3,
    )
    assert len(selected) == 3
    assert all(t.prediction.confidence >= 75 for t in selected)
    assert all(2.25 <= t.prediction.display_odds <= 3.75 for t in selected)


def test_parse_command_strips_bot_mention():
    assert parse_command("/tips@MyFootballBot") == "/tips"
    assert parse_command("/status") == "/status"


def test_status_format_includes_commands():
    status = RuntimeStatus(safety_min_confidence=75, target_odds=3.0, max_daily_tips=3)
    status.mark_scan(fixtures=10, predictions=40, tips=2, summary="Demo tips")
    text = status.format_status()
    assert "BOT STATUS" in text
    assert "/status" in text
    assert "75%" in text


def test_command_bot_status_and_unauthorized():
    sent: list[tuple[str, str | None]] = []

    class FakeTg(TelegramAlerter):
        def __init__(self):
            super().__init__("token", "111")

        def send(self, text: str, chat_id: str | None = None) -> bool:
            sent.append((text, chat_id))
            return True

    status = RuntimeStatus()
    bot = TelegramCommandBot(
        FakeTg(),
        status,
        allowed_chat_ids={"111"},
        on_tips=lambda: "cached tips",
        on_safety_refresh=lambda: "fresh safety",
        on_band=lambda key: f"band-{key}",
        on_fixtures=lambda: "fixtures list",
    )
    bot.handle_update(
        {"message": {"text": "/status", "chat": {"id": 111}}}
    )
    assert sent and "BOT STATUS" in sent[-1][0]

    bot.handle_update(
        {"message": {"text": "/tips", "chat": {"id": 111}}}
    )
    assert sent[-1][0] == "cached tips"

    bot.handle_update(
        {"message": {"text": "/safety", "chat": {"id": 999}}}
    )
    assert "Unauthorized" in sent[-1][0]
