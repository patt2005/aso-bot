"""Aggregate keywords from validated competitors and split into BEST/MEDIUM/TRASH.

Scoring intuition:
  score = popularity_avg * sqrt(competitor_count) / (avg_competitor_ranking + 1)

  - popularity_avg: how big is the search volume
  - sqrt(competitor_count): more competitors using it = niche-validated, but
    diminishing returns (sqrt instead of linear)
  - 1 / (avg_ranking + 1): if competitors rank top-10, the keyword is reachable
"""
from __future__ import annotations
import math
from collections import defaultdict

from core.models import Competitor, ScoredKeyword
from core.keyword_filter import normalize, is_acceptable_language


def aggregate_keywords(
    competitors: list[Competitor],
    allowed_languages: list[str] | None = None,
) -> list[ScoredKeyword]:
    bucket: dict[str, dict] = defaultdict(lambda: {
        "popularities": [],
        "rankings": [],
        "best_rank_per_comp": {},
        "total_apps": [],
        "ad_counts": [],
    })

    for comp in competitors:
        if not comp.validated:
            continue
        for kw in comp.keywords:
            if allowed_languages is not None and not is_acceptable_language(kw.name, allowed_languages):
                continue
            entry = bucket[normalize(kw.name)]
            if kw.popularity is not None:
                entry["popularities"].append(kw.popularity)
            if kw.ranking is not None:
                entry["rankings"].append(kw.ranking)
            if kw.total_apps is not None:
                entry["total_apps"].append(kw.total_apps)
            if kw.ad_count is not None:
                entry["ad_counts"].append(kw.ad_count)
            rank = kw.ranking if kw.ranking is not None else 9999
            prev = entry["best_rank_per_comp"].get(comp.app_id)
            if prev is None or rank < prev:
                entry["best_rank_per_comp"][comp.app_id] = rank

    scored: list[ScoredKeyword] = []
    for name, data in bucket.items():
        pop_avg = sum(data["popularities"]) / len(data["popularities"]) if data["popularities"] else 0
        rank_avg = sum(data["rankings"]) / len(data["rankings"]) if data["rankings"] else 100
        comps_by_rank = sorted(data["best_rank_per_comp"].items(), key=lambda x: x[1])
        sorted_app_ids = [app_id for app_id, _ in comps_by_rank]
        count = len(sorted_app_ids)
        score = pop_avg * math.sqrt(count) / (rank_avg + 1)
        total_apps = max(data["total_apps"]) if data["total_apps"] else None
        ad_count = max(data["ad_counts"]) if data["ad_counts"] else None
        scored.append(ScoredKeyword(
            name=name,
            popularity=round(pop_avg, 1),
            avg_competitor_ranking=round(rank_avg, 1),
            competitor_count=count,
            competitors=sorted_app_ids,
            competitor_ranks={aid: r for aid, r in comps_by_rank if r < 9999},
            score=round(score, 3),
            total_apps=total_apps,
            ad_count=ad_count,
        ))

    scored.sort(key=lambda s: s.score, reverse=True)
    return scored


def classify(scored: list[ScoredKeyword]) -> dict[str, list[ScoredKeyword]]:
    """Split scored keywords into BEST / MEDIUM / TRASH tiers.

    Defensive numeric coercion — some cached keywords can come back with a
    None / str field which would crash the comparisons here.
    """
    best, medium, trash = [], [], []

    for kw in scored:
        pop = _to_float(kw.popularity)
        rank = _to_float(kw.avg_competitor_ranking, default=100.0)
        count = int(kw.competitor_count or 0)

        if count == 1 and pop < 15:
            kw.tier = "TRASH"
            trash.append(kw)
            continue

        if pop >= 30 and count >= 3 and rank <= 15:
            kw.tier = "BEST"
            best.append(kw)
        elif (pop >= 15 and count >= 2) or (pop >= 25 and rank <= 30):
            kw.tier = "MEDIUM"
            medium.append(kw)
        else:
            kw.tier = "TRASH"
            trash.append(kw)

    return {"BEST": best, "MEDIUM": medium, "TRASH": trash}


def _to_float(value, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
