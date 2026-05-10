from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Keyword:
    name: str
    ranking: Optional[int] = None
    change: Optional[int] = None
    popularity: Optional[float] = None
    total_apps: Optional[int] = None
    ad_count: Optional[int] = None

    def __str__(self) -> str:
        parts = [self.name]
        if self.ranking is not None:
            parts.append(f"rank={self.ranking}")
        if self.popularity is not None:
            parts.append(f"pop={self.popularity}")
        return " | ".join(parts)


@dataclass
class Competitor:
    app_id: str
    name: str = ""
    category: str = ""
    seed_overlap: float = 0.0
    matched_seeds: list[str] = field(default_factory=list)
    validated: bool = False
    keywords: list[Keyword] = field(default_factory=list)


@dataclass
class ScoredKeyword:
    name: str
    popularity: float
    avg_competitor_ranking: float
    competitor_count: int
    competitors: list[str] = field(default_factory=list)
    score: float = 0.0
    tier: str = "TRASH"
    total_apps: Optional[int] = None
    ad_count: Optional[int] = None
    bidder_ids: list[str] = field(default_factory=list)
    source: str = "ASO"
    competitor_ranks: dict[str, int] = field(default_factory=dict)
