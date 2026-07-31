"""Tests for multi-band (3/5/50) selection and Telegram commands."""

from __future__ import annotations

from datetime import datetime, timezone

from src.analysis.poisson import correct_score_probabilities, market_probabilities
from src.models import Fixture, MarketPrediction, Tip
from src.runtime_status import RuntimeStatus
from src.selector import OddsBand, select_best_for_band
from src.telegram_alerter import TelegramAlerter
from src.telegram_bot import TelegramCommandBot, parse_command


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


def test_correct_scores_exist():
    cs = correct_score_probabilities(1.6, 1.1)
    assert "cs_1_0" in cs
    assert cs["cs_1_0"] > 0
    probs = market_probabilities(1.6, 1.1)
    assert "over_45" in probs
    assert "home_win_nil" in probs


def test_best_3odd_band_picks_closest_high_confidence():
    tips = [
        _tip("1", "PL", "draw", 3.05, 82),
        _tip("2", "PD", "away_win", 2.5, 88),
        _tip("3", "BL1", "draw", 3.5, 70),
        _tip("4", "FL1", "over_25", 1.9, 90),
    ]
    band = OddsBand(
        key="3odd",
        title="BEST 3-ODD",
        target_odds=3.0,
        tolerance=0.75,
        min_confidence=75,
        max_tips=2,
        prefer_safety_markets=True,
    )
    selected = select_best_for_band(tips, band)
    assert 1 <= len(selected) <= 2
    assert all(t.prediction.confidence >= 75 for t in selected)
    # Closest to 3.0 among high-conf should rank first
    assert abs(selected[0].prediction.display_odds - 3.0) <= 0.75


def test_5odd_and_50odd_bands():
    tips = [
        _tip("a", "PL", "away_win", 5.1, 72),
        _tip("b", "PD", "over_35", 4.8, 74),
        _tip("c", "BL1", "cs_3_0", 48.0, 68),
        _tip("d", "FL1", "cs_0_3", 55.0, 65),
        _tip("e", "SA", "cs_4_1", 80.0, 62),
        _tip("f", "PL", "draw", 3.0, 80),
    ]
    band5 = OddsBand("5odd", "5", 5.0, 1.25, 70.0, 3)
    band50 = OddsBand("50odd", "50", 50.0, 20.0, 60.0, 3)
    s5 = select_best_for_band(tips, band5)
    s50 = select_best_for_band(tips, band50)
    assert len(s5) >= 1
    assert all(3.75 <= t.prediction.display_odds <= 6.25 for t in s5)
    assert len(s50) >= 1
    assert all(30 <= t.prediction.display_odds <= 70 for t in s50)


def test_telegram_band_commands():
    sent: list[str] = []

    class FakeTg(TelegramAlerter):
        def __init__(self):
            super().__init__("token", "111")

        def send(self, text: str, chat_id: str | None = None) -> bool:
            sent.append(text)
            return True

    bot = TelegramCommandBot(
        FakeTg(),
        RuntimeStatus(),
        allowed_chat_ids={"111"},
        on_tips=lambda: "ALL BOARD",
        on_band=lambda key: f"BAND:{key}",
        on_safety_refresh=lambda: "REFRESHED",
    )
    bot.handle_update({"message": {"text": "/3odd", "chat": {"id": 111}}})
    assert sent[-1] == "BAND:3odd"
    bot.handle_update({"message": {"text": "/5odd@Bot", "chat": {"id": 111}}})
    assert sent[-1] == "BAND:5odd"
    bot.handle_update({"message": {"text": "/50odd", "chat": {"id": 111}}})
    assert sent[-1] == "BAND:50odd"
    assert parse_command("/50odd@x") == "/50odd"
