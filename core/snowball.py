"""Snowball expansion: turn discovered bidders into extra competitors.

After the bidding scraper has cached bidder lists per keyword, we collect every
unique bidder app and check whether they belong to OUR niche. Two filters:

  1. Cheap name heuristic — keyword tokens in the app's display name.
  2. Hard Jaccard overlap — scrape the candidate's organic keywords and
     require 30% overlap with our seeds.

Bidders that pass become extra Competitor objects so their organic keywords
join the pool. The result: only commercially-validated, niche-relevant
expansion (no generic noise from random advertisers).
"""
from __future__ import annotations
import re
from collections import defaultdict
from typing import Iterable

from core.models import Competitor, Keyword
from core.keyword_scraper import get_keywords
from core.keyword_filter import normalize


NICHE_TOKENS = {
    "call", "recorder", "recording", "voice", "phone", "tape", "rec",
    "inregistrare", "apel", "reportofon", "convorbire",
}


def _name_passes(name: str) -> bool:
    if not name:
        return False
    words = re.findall(r"[a-zA-Zăâîșț]+", name.lower())
    return any(w in NICHE_TOKENS for w in words)


def _jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa = {normalize(x) for x in a if x}
    sb = {normalize(x) for x in b if x}
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def collect_unique_bidders(bidding_map: dict[str, dict]) -> list[dict]:
    """Walk the bidding_map (keyword -> summary) and dedup bidders by app_id."""
    seen: dict[str, dict] = {}
    for kw, info in bidding_map.items():
        names = info.get("top_bidders") or []
        ids = info.get("bidder_ids") or []
        for app_id, name in zip(ids, names):
            if app_id and app_id not in seen:
                seen[app_id] = {"app_id": app_id, "name": name}
    return list(seen.values())


def find_relevant_bidders(
    bidding_map: dict[str, dict],
    seed_keywords: list[str],
    country: int,
    existing_app_ids: set[str],
    jaccard_threshold: float = 0.10,
    log=print,
) -> list[Competitor]:
    """Return new Competitor objects for bidders that pass both filters.

    `existing_app_ids` lets us skip apps already in the organic competitor pool.
    """
    candidates = collect_unique_bidders(bidding_map)
    log(f"  {len(candidates)} unique bidders discovered")

    fresh = [c for c in candidates if c["app_id"] not in existing_app_ids]
    log(f"  {len(fresh)} bidders are NEW (not in organic pool)")

    name_passed = [c for c in fresh if _name_passes(c["name"])]
    log(f"  {len(name_passed)} pass name heuristic (niche tokens)")

    accepted: list[Competitor] = []
    seeds_norm = [normalize(s) for s in seed_keywords]

    for i, cand in enumerate(name_passed, 1):
        try:
            kws = get_keywords(cand["app_id"], country=country)
        except Exception as exc:
            log(f"    [{i}/{len(name_passed)}] {cand['name'][:30]} skip ({exc})")
            continue
        kw_names = [k.name for k in kws if k.name]
        overlap = _jaccard(kw_names, seeds_norm)
        marker = "✓" if overlap >= jaccard_threshold else "✗"
        log(f"    [{i}/{len(name_passed)}] {marker} {cand['name'][:30]:30s} kw={len(kws)} overlap={overlap:.0%}")
        if overlap >= jaccard_threshold:
            comp = Competitor(
                app_id=cand["app_id"],
                name=cand["name"],
                category="paid",
                seed_overlap=overlap,
                matched_seeds=sorted({n for n in kw_names if normalize(n) in seeds_norm}),
                validated=True,
                keywords=kws,
            )
            accepted.append(comp)

    log(f"  {len(accepted)} bidders accepted (overlap >= {jaccard_threshold:.0%})")
    return accepted
