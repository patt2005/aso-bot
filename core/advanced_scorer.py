"""Multi-factor keyword scoring on top of validated competitors.

Computes per-keyword signals (variance, length class, brand match, locale,
difficulty, opportunity, composite score) and assigns each keyword to one or
more strategic tiers (WINNERS, EASY_WINS, HIGH_VALUE, HIDDEN_GEMS, LOCAL_PLAYS,
AVOID). Walks competitors directly so per-competitor ranking detail survives
into the variance/min/max computation.

Stdlib only. Backward compatible: does not modify core/scorer.py.
"""
from __future__ import annotations

import math
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field

from core.models import Competitor, ScoredKeyword


KNOWN_BRANDS: set[str] = {
    "tapeacall",
    "tape a call",
    "tape-a-call",
    "trapcall",
    "trap call",
    "callapp",
    "call app",
    "truecaller",
    "true caller",
    "icall",
    "i call",
    "cube acr",
    "cube call recorder",
    "rev call recorder",
    "rev recorder",
    "automatic call recorder",
    "acr",
    "boldbeast",
    "callrec",
    "call rec",
}

_LOCAL_TOKENS_RO: set[str] = {
    "inregistrare",
    "inregistrari",
    "inregistrator",
    "apel",
    "apeluri",
    "telefon",
    "telefoane",
    "convorbire",
    "convorbiri",
    "reportofon",
    "reportofoane",
    "inregistreaza",
    "inregistra",
    "inregistrarea",
}

_RO_DIACRITICS = re.compile(r"[ăâîșțĂÂÎȘȚ]")
_TOKEN_SPLIT = re.compile(r"[^a-zA-Z\u0100-\u024F]+")
_WORD_SPLIT = re.compile(r"\s+")


def _length_class(name: str) -> str:
    parts = [p for p in _WORD_SPLIT.split(name.strip()) if p]
    n = len(parts)
    if n <= 1:
        return "single"
    if n == 2:
        return "short"
    return "long_tail"


def _length_bonus(length_class: str) -> float:
    if length_class == "long_tail":
        return 1.5
    if length_class == "short":
        return 1.2
    return 1.0


def _is_brand_keyword(name: str) -> bool:
    candidate = name.strip().lower()
    if candidate in KNOWN_BRANDS:
        return True
    tokens = [t for t in _TOKEN_SPLIT.split(candidate) if t]
    token_set = set(tokens)
    for brand in KNOWN_BRANDS:
        brand_norm = brand.strip().lower()
        if not brand_norm:
            continue
        if brand_norm == candidate:
            return True
        brand_tokens = [t for t in _TOKEN_SPLIT.split(brand_norm) if t]
        if len(brand_tokens) == 1:
            if brand_tokens[0] in token_set and len(brand_tokens[0]) >= 5:
                return True
        else:
            joined = " ".join(tokens)
            if f" {brand_norm} " in f" {joined} ":
                return True
    return False


def _is_local_language(name: str, country_iso: str) -> bool:
    iso = (country_iso or "").upper()
    if iso != "RO":
        return False
    if _RO_DIACRITICS.search(name):
        return True
    tokens = [t for t in _TOKEN_SPLIT.split(name.lower()) if t]
    return any(tok in _LOCAL_TOKENS_RO for tok in tokens)


def _safe_stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return statistics.stdev(values)


@dataclass
class AdvancedScoredKeyword:
    name: str
    popularity: float
    avg_competitor_ranking: float
    min_competitor_ranking: int
    max_competitor_ranking: int
    ranking_stddev: float
    competitor_count: int
    competitors: list[str]
    length_class: str
    is_brand_keyword: bool
    is_local_language: bool
    difficulty: float
    opportunity: float
    composite_score: float
    tiers: list[str] = field(default_factory=list)


def _normalize(name: str) -> str:
    return " ".join(name.lower().split())


def score_advanced(
    competitors: list[Competitor],
    country_iso: str = "RO",
) -> list[AdvancedScoredKeyword]:
    bucket: dict[str, dict] = defaultdict(lambda: {
        "popularities": [],
        "rankings": [],
        "competitors": [],
    })

    for comp in competitors:
        if not comp.validated:
            continue
        for kw in comp.keywords:
            key = _normalize(kw.name)
            if not key:
                continue
            entry = bucket[key]
            if kw.popularity is not None:
                entry["popularities"].append(float(kw.popularity))
            if kw.ranking is not None:
                entry["rankings"].append(int(kw.ranking))
            entry["competitors"].append(comp.app_id)

    scored: list[AdvancedScoredKeyword] = []
    for name, data in bucket.items():
        pops = data["popularities"]
        ranks = data["rankings"]
        unique_competitors = sorted(set(data["competitors"]))
        count = len(unique_competitors)

        pop_avg = sum(pops) / len(pops) if pops else 0.0
        avg_rank = sum(ranks) / len(ranks) if ranks else 100.0
        min_rank = min(ranks) if ranks else 100
        max_rank = max(ranks) if ranks else 100
        rank_stddev = _safe_stdev([float(r) for r in ranks])

        length_class = _length_class(name)
        brand = _is_brand_keyword(name)
        local = _is_local_language(name, country_iso)

        difficulty_raw = (pop_avg / 100.0) * (count / 10.0) * (1.0 - rank_stddev / 30.0)
        difficulty = max(0.0, min(1.0, difficulty_raw))

        bonus = _length_bonus(length_class)
        reachability = 1.0 / (avg_rank + 1.0)
        opportunity_raw = (1.0 - difficulty) * reachability * (pop_avg / 100.0) * bonus
        opportunity = max(0.0, min(1.0, opportunity_raw))

        composite = (
            0.4 * opportunity
            + 0.3 * (pop_avg / 100.0)
            + 0.2 * (1.0 - avg_rank / 100.0)
            + 0.1 * (1.0 if local else 0.7)
        )
        if brand:
            composite *= 1.3
        composite = max(0.0, min(1.0, composite))

        scored.append(AdvancedScoredKeyword(
            name=name,
            popularity=round(pop_avg, 1),
            avg_competitor_ranking=round(avg_rank, 1),
            min_competitor_ranking=min_rank,
            max_competitor_ranking=max_rank,
            ranking_stddev=round(rank_stddev, 3),
            competitor_count=count,
            competitors=unique_competitors,
            length_class=length_class,
            is_brand_keyword=brand,
            is_local_language=local,
            difficulty=round(difficulty, 4),
            opportunity=round(opportunity, 4),
            composite_score=round(composite, 4),
        ))

    scored.sort(key=lambda s: s.composite_score, reverse=True)
    return scored


def _tiers_for(kw: AdvancedScoredKeyword) -> list[str]:
    tiers: list[str] = []

    if kw.composite_score >= 0.6 and kw.competitor_count >= 3:
        tiers.append("WINNERS")

    is_long_tail = kw.length_class == "long_tail"
    if is_long_tail or (kw.is_brand_keyword and kw.opportunity >= 0.4):
        tiers.append("EASY_WINS")

    if kw.popularity >= 50 and kw.composite_score >= 0.4:
        tiers.append("HIGH_VALUE")

    if (
        2 <= kw.competitor_count <= 3
        and kw.popularity >= 20
        and kw.avg_competitor_ranking <= 25
    ):
        tiers.append("HIDDEN_GEMS")

    if kw.is_local_language and kw.popularity >= 15:
        tiers.append("LOCAL_PLAYS")

    if kw.composite_score < 0.2 or (kw.popularity < 10 and kw.competitor_count < 3):
        tiers.append("AVOID")

    return tiers


def classify_advanced(
    scored: list[AdvancedScoredKeyword],
) -> dict[str, list[AdvancedScoredKeyword]]:
    tier_names = [
        "WINNERS",
        "EASY_WINS",
        "HIGH_VALUE",
        "HIDDEN_GEMS",
        "LOCAL_PLAYS",
        "AVOID",
    ]
    out: dict[str, list[AdvancedScoredKeyword]] = {t: [] for t in tier_names}

    for kw in scored:
        kw.tiers = _tiers_for(kw)
        for t in kw.tiers:
            out[t].append(kw)

    for t in tier_names:
        out[t].sort(key=lambda k: k.composite_score, reverse=True)

    return out


__all__ = [
    "KNOWN_BRANDS",
    "AdvancedScoredKeyword",
    "score_advanced",
    "classify_advanced",
]
