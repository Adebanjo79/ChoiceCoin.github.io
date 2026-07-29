"""Domain models for fixtures, team stats, and tips."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class TeamForm:
    team_id: int | str
    team_name: str
    played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    goals_against: int = 0
    home_played: int = 0
    home_gf: int = 0
    home_ga: int = 0
    away_played: int = 0
    away_gf: int = 0
    away_ga: int = 0
    recent_results: list[str] = field(default_factory=list)  # W/D/L newest last

    @property
    def points(self) -> int:
        return self.wins * 3 + self.draws

    @property
    def avg_gf(self) -> float:
        return self.goals_for / self.played if self.played else 1.2

    @property
    def avg_ga(self) -> float:
        return self.goals_against / self.played if self.played else 1.2

    @property
    def home_avg_gf(self) -> float:
        return self.home_gf / self.home_played if self.home_played else self.avg_gf

    @property
    def home_avg_ga(self) -> float:
        return self.home_ga / self.home_played if self.home_played else self.avg_ga

    @property
    def away_avg_gf(self) -> float:
        return self.away_gf / self.away_played if self.away_played else self.avg_gf

    @property
    def away_avg_ga(self) -> float:
        return self.away_ga / self.away_played if self.away_played else self.avg_ga

    @property
    def form_score(self) -> float:
        """0–1 score from last results (recent weighted higher)."""
        if not self.recent_results:
            return 0.5
        weights = [0.5 + i * 0.1 for i in range(len(self.recent_results))]
        mapping = {"W": 1.0, "D": 0.45, "L": 0.0}
        total_w = sum(weights)
        return sum(mapping.get(r, 0.3) * w for r, w in zip(self.recent_results, weights)) / total_w


@dataclass
class Fixture:
    id: str
    league_code: str
    league_name: str
    kickoff: datetime
    home_team: str
    away_team: str
    home_team_id: int | str = ""
    away_team_id: int | str = ""
    status: str = "SCHEDULED"
    matchday: int | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def label(self) -> str:
        return f"{self.home_team} vs {self.away_team}"


@dataclass
class MarketPrediction:
    market: str
    market_label: str
    probability: float  # model probability 0–1
    fair_odds: float
    book_odds: float | None  # bookmaker odds when available
    confidence: float  # 0–100 composite confidence
    edge: float  # model_prob - implied_book_prob (or 0 if no book)
    reasons: list[str] = field(default_factory=list)

    @property
    def display_odds(self) -> float:
        return self.book_odds if self.book_odds and self.book_odds > 1 else self.fair_odds


@dataclass
class Tip:
    fixture: Fixture
    prediction: MarketPrediction
    rank_score: float = 0.0

    def is_actionable(self, min_confidence: float = 70.0) -> bool:
        return self.prediction.confidence >= min_confidence

    def to_dict(self) -> dict[str, Any]:
        p = self.prediction
        f = self.fixture
        return {
            "league": f.league_name,
            "league_code": f.league_code,
            "match": f.label,
            "kickoff": f.kickoff.isoformat(),
            "market": p.market_label,
            "market_key": p.market,
            "confidence": round(p.confidence, 1),
            "probability": round(p.probability * 100, 1),
            "odds": round(p.display_odds, 2),
            "fair_odds": round(p.fair_odds, 2),
            "book_odds": round(p.book_odds, 2) if p.book_odds else None,
            "edge": round(p.edge * 100, 1),
            "reasons": p.reasons,
        }
