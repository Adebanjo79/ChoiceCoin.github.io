"""SportyBet.com booking / share codes (loadable in the SportyBet betslip)."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

from src.models import Tip

logger = logging.getLogger(__name__)

try:
    from curl_cffi import requests as cffi_requests

    SPORTYBET_AVAILABLE = True
except ImportError:  # pragma: no cover - optional runtime dep
    cffi_requests = None  # type: ignore
    SPORTYBET_AVAILABLE = False

SPORT_ID = "sr:sport:1"
DEFAULT_COUNTRY = "ng"

TOURNAMENT_MAP: dict[str, str] = {
    "PL": "sr:tournament:17",
    "PD": "sr:tournament:8",
    "SA": "sr:tournament:23",
    "BL1": "sr:tournament:35",
    "FL1": "sr:tournament:34",
    "DED": "sr:tournament:37",
    "ELC": "sr:tournament:18",
    "PPL": "sr:tournament:238",
    "BSA": "sr:tournament:325",
    "CL": "sr:tournament:7",
    "CLI": "sr:tournament:384",
}

# Our market key → (marketId, outcomeId, specifier)
MARKET_MAP: dict[str, tuple[str, str, str]] = {
    "home_win": ("1", "1", ""),
    "draw": ("1", "2", ""),
    "away_win": ("1", "3", ""),
    "home_or_draw": ("10", "9", ""),
    "away_or_draw": ("10", "11", ""),
    "over_25": ("18", "12", "total=2.5"),
    "under_25": ("18", "13", "total=2.5"),
    "over_35": ("18", "12", "total=3.5"),
    "under_35": ("18", "13", "total=3.5"),
    "over_45": ("18", "12", "total=4.5"),
    "under_45": ("18", "13", "total=4.5"),
    "btts_yes": ("29", "74", ""),
    "btts_no": ("29", "76", ""),
    "home_win_nil": ("33", "74", ""),
    "away_win_nil": ("34", "74", ""),
}

# Correct Score market 45 outcome IDs: home 0–4, away 0–4
# id = 274 + away * 10 + home * 2


@dataclass
class SportyBetBooking:
    share_code: str
    share_url: str
    event_id: str = ""
    matched: int = 0
    failed: int = 0


def sportybet_enabled(settings) -> bool:
    if not getattr(settings, "sportybet_enabled", True):
        return False
    return SPORTYBET_AVAILABLE


def market_selection(market_key: str) -> tuple[str, str, str] | None:
    """Map tip market key → SportyBet (marketId, outcomeId, specifier)."""
    if market_key in MARKET_MAP:
        return MARKET_MAP[market_key]
    if market_key.startswith("cs_"):
        parts = market_key.split("_")
        if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
            home, away = int(parts[1]), int(parts[2])
            if 0 <= home <= 4 and 0 <= away <= 4:
                outcome_id = str(274 + away * 10 + home * 2)
                return ("45", outcome_id, "")
    return None


def _normalize(name: str) -> str:
    cleaned = (
        name.lower()
        .replace("&", " and ")
        .replace("-", " ")
        .replace(".", " ")
        .replace(" fc", "")
        .replace(" cf", "")
        .replace(" afc", "")
        .replace(" united", " utd")
    )
    return " ".join(cleaned.split())


def _fuzzy_score(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


class SportyBetClient:
    """Public SportyBet Nigeria API (Chrome TLS impersonation)."""

    def __init__(self, country: str = DEFAULT_COUNTRY) -> None:
        self.country = (country or DEFAULT_COUNTRY).strip().lower() or DEFAULT_COUNTRY
        self.base = f"https://www.sportybet.com/api/{self.country}"
        self.headers = {
            "Referer": f"https://www.sportybet.com/{self.country}/",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://www.sportybet.com",
        }
        self._catalog_cache: dict[str, list[dict[str, Any]]] = {}
        self._event_cache: dict[tuple[str, str, str], dict[str, Any] | None] = {}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        if not SPORTYBET_AVAILABLE:
            return None
        url = f"{self.base}{path}"
        chrome = random.choice(("chrome131", "chrome124", "chrome120"))
        try:
            time.sleep(random.uniform(0.15, 0.45))
            resp = cffi_requests.get(
                url,
                headers=self.headers,
                params=params,
                impersonate=chrome,
                timeout=20,
            )
            if resp.status_code != 200:
                logger.warning("SportyBet GET %s → %s", path, resp.status_code)
                return None
            data = resp.json()
            if data.get("bizCode") != 10000:
                logger.warning(
                    "SportyBet GET %s → bizCode=%s msg=%s",
                    path,
                    data.get("bizCode"),
                    data.get("message"),
                )
                return None
            return data
        except Exception as exc:  # pragma: no cover - network
            logger.warning("SportyBet GET %s failed: %s", path, exc)
            return None

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not SPORTYBET_AVAILABLE:
            return None
        url = f"{self.base}{path}"
        chrome = random.choice(("chrome131", "chrome124", "chrome120"))
        try:
            time.sleep(random.uniform(0.15, 0.4))
            resp = cffi_requests.post(
                url,
                headers=self.headers,
                json=payload,
                impersonate=chrome,
                timeout=20,
            )
            if resp.status_code != 200:
                logger.warning("SportyBet POST %s → %s", path, resp.status_code)
                return None
            data = resp.json()
            if data.get("bizCode") != 10000:
                logger.warning(
                    "SportyBet POST %s → bizCode=%s msg=%s",
                    path,
                    data.get("bizCode"),
                    data.get("message") or data.get("innerMsg"),
                )
                return None
            return data
        except Exception as exc:  # pragma: no cover - network
            logger.warning("SportyBet POST %s failed: %s", path, exc)
            return None

    def event_catalog(self, match_date: str | None = None) -> list[dict[str, Any]]:
        """Upcoming football events. Pass match_date (YYYY-MM-DD) to filter; None = all."""
        cache_key = match_date or "__all__"
        if cache_key in self._catalog_cache:
            return self._catalog_cache[cache_key]

        data = self._get(
            "/factsCenter/commonThumbnailEvents",
            params={"sportId": SPORT_ID, "marketId": "1"},
        )
        if not data:
            self._catalog_cache[cache_key] = []
            return []

        all_events: list[dict[str, Any]] = []
        for group in data.get("data") or []:
            if not isinstance(group, dict):
                continue
            for ev in group.get("events") or []:
                start_ms = ev.get("estimateStartTime")
                home = ev.get("homeTeamName") or ""
                away = ev.get("awayTeamName") or ""
                if not home or not away:
                    continue
                tournament = (
                    ((ev.get("sport") or {}).get("category") or {}).get("tournament") or {}
                )
                if "SRL" in str(tournament.get("name") or ""):
                    continue
                all_events.append(
                    {
                        "eventId": ev.get("eventId", ""),
                        "homeTeamName": home,
                        "awayTeamName": away,
                        "tournament_id": tournament.get("id", ""),
                        "estimateStartTime": start_ms,
                        "date": (
                            datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).strftime(
                                "%Y-%m-%d"
                            )
                            if start_ms
                            else ""
                        ),
                    }
                )

        self._catalog_cache["__all__"] = all_events
        # also cache per-day slices
        by_day: dict[str, list[dict[str, Any]]] = {}
        for ev in all_events:
            d = ev.get("date") or ""
            if d:
                by_day.setdefault(d, []).append(ev)
        for d, rows in by_day.items():
            self._catalog_cache[d] = rows

        if match_date:
            result = self._catalog_cache.get(match_date, [])
        else:
            result = all_events
        logger.info(
            "SportyBet catalog: %d events%s",
            len(result),
            f" on {match_date}" if match_date else " (all)",
        )
        return result

    def find_event(
        self,
        home_team: str,
        away_team: str,
        league_code: str = "",
        match_date: str | None = None,
    ) -> dict[str, Any] | None:
        cache_key = (home_team.lower(), away_team.lower(), (match_date or "")[:10])
        if cache_key in self._event_cache:
            return self._event_cache[cache_key]

        tournament_id = TOURNAMENT_MAP.get(league_code.upper()) if league_code else None
        # Prefer exact date, then full catalog (covers timezone / slate mismatches)
        pools: list[list[dict[str, Any]]] = []
        if match_date:
            pools.append(self.event_catalog(match_date[:10]))
        pools.append(self.event_catalog(None))

        best: dict[str, Any] | None = None
        best_score = 0.0
        seen: set[str] = set()
        for catalog in pools:
            candidates = catalog
            if tournament_id:
                narrowed = [e for e in catalog if e.get("tournament_id") == tournament_id]
                if narrowed:
                    candidates = narrowed
            for ev in candidates:
                eid = ev.get("eventId") or ""
                if eid in seen:
                    continue
                seen.add(eid)
                score = (
                    _fuzzy_score(home_team, ev.get("homeTeamName", ""))
                    + _fuzzy_score(away_team, ev.get("awayTeamName", ""))
                ) / 2
                # Prefer same-day matches when date known
                if match_date and ev.get("date") == match_date[:10]:
                    score += 0.05
                if score > best_score:
                    best_score = score
                    best = ev

        if best_score < 0.55:
            logger.debug(
                "SportyBet: no event for %s vs %s (best=%.2f)",
                home_team,
                away_team,
                best_score,
            )
            self._event_cache[cache_key] = None
            return None

        self._event_cache[cache_key] = best
        return best

    def create_booking(self, selections: list[dict[str, str]]) -> SportyBetBooking | None:
        if not selections:
            return None
        data = self._post("/orders/share", {"selections": selections})
        if not data:
            return None
        payload = data.get("data") or {}
        code = payload.get("shareCode")
        if not code:
            return None
        url = payload.get("shareURL") or (
            f"https://www.sportybet.com/{self.country}/?shareCode={code}"
        )
        return SportyBetBooking(
            share_code=str(code),
            share_url=str(url).replace("http://", "https://"),
            event_id=selections[0].get("eventId", ""),
            matched=len(selections),
        )

    def selection_for_tip(self, tip: Tip) -> dict[str, str] | None:
        mapped = market_selection(tip.prediction.market)
        if not mapped:
            return None
        event = self.find_event(
            tip.fixture.home_team,
            tip.fixture.away_team,
            tip.fixture.league_code,
            tip.fixture.kickoff.strftime("%Y-%m-%d"),
        )
        if not event or not event.get("eventId"):
            return None
        market_id, outcome_id, specifier = mapped
        return {
            "eventId": str(event["eventId"]),
            "marketId": market_id,
            "outcomeId": outcome_id,
            "specifier": specifier,
            "sportId": SPORT_ID,
        }

    def book_tip(self, tip: Tip) -> SportyBetBooking | None:
        sel = self.selection_for_tip(tip)
        if not sel:
            return None
        booking = self.create_booking([sel])
        if booking:
            tip.sportybet_code = booking.share_code
            tip.sportybet_url = booking.share_url
        return booking

    def book_tips_multi(self, tips: list[Tip]) -> SportyBetBooking | None:
        """One SportyBet booking code for several singles (acca-style load)."""
        selections: list[dict[str, str]] = []
        seen_events: set[str] = set()
        failed = 0
        for tip in tips:
            sel = self.selection_for_tip(tip)
            if not sel:
                failed += 1
                continue
            eid = sel["eventId"]
            if eid in seen_events:
                failed += 1
                continue
            seen_events.add(eid)
            selections.append(sel)
        if not selections:
            return None
        booking = self.create_booking(selections)
        if booking:
            booking.failed = failed
            booking.matched = len(selections)
        return booking


def attach_sportybet_codes(
    tips: list[Tip],
    *,
    country: str = DEFAULT_COUNTRY,
    client: SportyBetClient | None = None,
) -> dict[str, SportyBetBooking]:
    """Attach per-tip SportyBet codes. Returns empty dict if unavailable."""
    if not SPORTYBET_AVAILABLE:
        logger.warning("curl_cffi missing — SportyBet booking codes disabled")
        return {}
    sb = client or SportyBetClient(country=country)
    for tip in tips:
        try:
            sb.book_tip(tip)
        except Exception as exc:  # pragma: no cover
            logger.warning("SportyBet book_tip failed: %s", tip.fixture.label, exc)
    return {}


def book_band_codes(
    tips_by_band: dict[str, list[Tip]],
    *,
    country: str = DEFAULT_COUNTRY,
    client: SportyBetClient | None = None,
) -> dict[str, SportyBetBooking]:
    """Create one multi booking code per odds band."""
    if not SPORTYBET_AVAILABLE:
        return {}
    sb = client or SportyBetClient(country=country)
    out: dict[str, SportyBetBooking] = {}
    for band, tips in tips_by_band.items():
        if not tips:
            continue
        try:
            booking = sb.book_tips_multi(tips)
        except Exception as exc:  # pragma: no cover
            logger.warning("SportyBet band %s failed: %s", band, exc)
            continue
        if booking:
            out[band] = booking
            logger.info(
                "SportyBet %s code=%s legs=%d",
                band,
                booking.share_code,
                booking.matched,
            )
    return out


def book_accumulator_options(
    accus_by_band: dict[str, list],
    *,
    country: str = DEFAULT_COUNTRY,
    client: SportyBetClient | None = None,
) -> dict[str, SportyBetBooking]:
    """Attach a SportyBet booking code to every accumulator option.

    Returns a map of first-option codes per band (for status summaries).
    """
    if not SPORTYBET_AVAILABLE:
        return {}
    sb = client or SportyBetClient(country=country)
    first_codes: dict[str, SportyBetBooking] = {}
    for band, accus in accus_by_band.items():
        for acc in accus:
            try:
                booking = sb.book_tips_multi(list(acc.legs))
            except Exception as exc:  # pragma: no cover
                logger.warning("SportyBet option %s failed: %s", acc.label, exc)
                continue
            if not booking:
                continue
            acc.sportybet_code = booking.share_code
            acc.sportybet_url = booking.share_url
            # also stamp legs for /codes detail views
            for leg in acc.legs:
                if not leg.sportybet_code:
                    leg.sportybet_code = booking.share_code
                    leg.sportybet_url = booking.share_url
            if band not in first_codes:
                first_codes[band] = booking
            logger.info(
                "SportyBet %s %s code=%s legs=%d",
                band,
                acc.label,
                booking.share_code,
                booking.matched,
            )
    return first_codes
