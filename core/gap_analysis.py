from __future__ import annotations
from dataclasses import dataclass
from math import sqrt
from typing import Optional

from core.models import Keyword, Competitor


@dataclass
class GapKeyword:
    name: str
    our_rank: Optional[int]
    avg_competitor_rank: float
    competitor_count: int
    popularity: float
    opportunity_score: float

    def __str__(self) -> str:
        rank_str = "absent" if self.our_rank is None else f"rank={self.our_rank}"
        return (
            f"{self.name} | {rank_str} | "
            f"comp_avg={self.avg_competitor_rank:.1f} (n={self.competitor_count}) | "
            f"pop={self.popularity:.0f} | score={self.opportunity_score:.2f}"
        )


def find_gap_keywords(
    our_keywords: list[Keyword],
    competitors: list[Competitor],
    min_competitor_count: int = 2,
    our_poor_rank_threshold: int = 50,
    min_popularity: float = 15,
) -> list[GapKeyword]:
    our: dict[str, Keyword] = {kw.name.lower(): kw for kw in our_keywords}

    # Aggregate per-keyword stats across validated competitors only.
    agg: dict[str, dict] = {}
    for comp in competitors:
        if not comp.validated:
            continue
        seen_in_comp: set[str] = set()
        for kw in comp.keywords:
            key = kw.name.lower()
            # Guard against the same competitor listing a keyword twice.
            if key in seen_in_comp:
                continue
            seen_in_comp.add(key)
            entry = agg.setdefault(
                key,
                {"name": kw.name, "ranks": [], "pop": 0.0, "count": 0},
            )
            if kw.ranking is not None:
                entry["ranks"].append(kw.ranking)
            if kw.popularity is not None and kw.popularity > entry["pop"]:
                entry["pop"] = kw.popularity
            entry["count"] += 1

    gaps: list[GapKeyword] = []
    for key, data in agg.items():
        count = data["count"]
        if count < min_competitor_count:
            continue
        popularity = data["pop"]
        if popularity < min_popularity:
            continue
        ranks = data["ranks"]
        # Without ranks we cannot compute an opportunity score.
        if not ranks:
            continue
        avg_rank = sum(ranks) / len(ranks)

        our_kw = our.get(key)
        our_rank = our_kw.ranking if our_kw and our_kw.ranking is not None else None

        if our_rank is not None and our_rank <= our_poor_rank_threshold:
            continue

        our_penalty = 1.0 if our_rank is None else 0.7
        score = (popularity * sqrt(count) / (avg_rank + 1)) * our_penalty

        gaps.append(
            GapKeyword(
                name=data["name"],
                our_rank=our_rank,
                avg_competitor_rank=avg_rank,
                competitor_count=count,
                popularity=popularity,
                opportunity_score=score,
            )
        )

    gaps.sort(key=lambda g: g.opportunity_score, reverse=True)
    return gaps


def find_owned_keywords(
    our_keywords: list[Keyword],
    top_rank_threshold: int = 20,
) -> list[Keyword]:
    owned = [
        kw for kw in our_keywords
        if kw.ranking is not None and kw.ranking <= top_rank_threshold
    ]
    owned.sort(key=lambda k: k.ranking)
    return owned


def summarize(gaps: list[GapKeyword], owned: list[Keyword]) -> str:
    lines = [
        "=== Gap Analysis Summary ===",
        f"Gap keywords found: {len(gaps)}",
        f"Owned keywords: {len(owned)}",
        "",
        "Top 5 gaps (highest opportunity):",
    ]
    if gaps:
        for g in gaps[:5]:
            lines.append(f"  - {g}")
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("Top 5 owned keywords:")
    if owned:
        for k in owned[:5]:
            lines.append(f"  - {k}")
    else:
        lines.append("  (none)")

    return "\n".join(lines)
