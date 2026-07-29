"""Unit tests for ETF retirement planner and recommendations (no live Telegram)."""

from __future__ import annotations

import pytest

from etfs import get_etf, list_etfs, recommend_for_monthly_retirement
from planner import (
    build_plan_summary,
    crash_and_return_reality_check,
    format_gbp,
    future_value_monthly,
    parse_plan_args,
)
from recommendations import (
    build_compare,
    build_etf_list,
    build_help,
    build_recommendation,
    format_etf_card,
)


def test_vwrp_is_top_balanced_pick() -> None:
    picks = recommend_for_monthly_retirement(100, 30, "balanced")
    assert picks[0].ticker == "VWRP"
    assert picks[0].share_class == "Acc"


def test_growth_includes_us_tilt() -> None:
    picks = recommend_for_monthly_retirement(100, 30, "growth")
    tickers = [e.ticker for e in picks[:4]]
    assert "VWRP" in tickers
    assert "VUAG" in tickers


def test_calm_includes_bonds() -> None:
    picks = recommend_for_monthly_retirement(100, 30, "calm")
    tickers = [e.ticker for e in picks[:4]]
    assert "VAGP" in tickers


def test_small_budget_drops_emerging_satellite() -> None:
    picks = recommend_for_monthly_retirement(100, 30, "balanced")
    assert all(e.ticker != "VFEM" for e in picks)


def test_get_etf_case_insensitive() -> None:
    assert get_etf("vwrp") is not None
    assert get_etf("VWRP") is not None
    assert get_etf("NOPE") is None


def test_list_etfs_sorted_by_score() -> None:
    etfs = list_etfs()
    scores = [e.suitability_score for e in etfs]
    assert scores == sorted(scores, reverse=True)


def test_future_value_zero_rate() -> None:
    proj = future_value_monthly(100, 10, 0)
    assert proj.total_contributed == 12_000
    assert proj.final_value == 12_000
    assert proj.growth == 0


def test_future_value_compound_grows() -> None:
    flat = future_value_monthly(100, 30, 0)
    growth = future_value_monthly(100, 30, 8)
    optimistic = future_value_monthly(100, 30, 15)
    assert growth.final_value > flat.final_value
    assert optimistic.final_value > growth.final_value
    assert growth.total_contributed == 36_000


def test_future_value_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError):
        future_value_monthly(-1, 10, 8)
    with pytest.raises(ValueError):
        future_value_monthly(100, 0, 8)
    with pytest.raises(ValueError):
        future_value_monthly(100, 10, -100)


def test_parse_plan_args_defaults_and_custom() -> None:
    assert parse_plan_args([]) == (100.0, 30, None)
    assert parse_plan_args(["150"]) == (150.0, 30, None)
    assert parse_plan_args(["100", "25"]) == (100.0, 25, None)
    assert parse_plan_args(["100", "30", "8"]) == (100.0, 30, 8.0)


def test_parse_plan_args_validation() -> None:
    with pytest.raises(ValueError):
        parse_plan_args(["0"])
    with pytest.raises(ValueError):
        parse_plan_args(["100", "0"])
    with pytest.raises(ValueError):
        parse_plan_args(["100", "30", "99"])


def test_format_gbp() -> None:
    assert format_gbp(99.5) == "£99.50"
    assert format_gbp(1500) == "£1,500"


def test_plan_summary_mentions_scenarios() -> None:
    text = build_plan_summary(100, 30)
    assert "Realistic" in text
    assert "15%" in text
    assert "£" in text


def test_reality_check_is_honest() -> None:
    text = crash_and_return_reality_check()
    assert "15%" in text
    assert "crash" in text.lower()
    assert "VWRP" in text


def test_recommendation_message() -> None:
    text = build_recommendation(100, 30, "balanced")
    assert "VWRP" in text
    assert "ISA" in text
    assert "not personalised" in text.lower() or "Educational" in text


def test_etf_list_and_card() -> None:
    etf = get_etf("VWRP")
    assert etf is not None
    card = format_etf_card(etf, rank=1)
    assert "1. VWRP" in card
    listing = build_etf_list()
    assert "VWRP" in listing
    assert "VUAG" in listing


def test_compare_two_etfs() -> None:
    text = build_compare(["VWRP", "VUAG"])
    assert "VWRP" in text
    assert "VUAG" in text
    assert "Quick take" in text


def test_compare_unknown() -> None:
    text = build_compare(["ZZZZ"])
    assert "Could not find" in text or "Unknown" in text or "Known" in text


def test_help_lists_commands() -> None:
    text = build_help()
    for cmd in ("/recommend", "/plan", "/reality", "/isa", "/compare"):
        assert cmd in text
