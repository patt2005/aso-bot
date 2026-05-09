"""Single source of truth for the niche-finder pipeline.

Every entry point (bot listener, CLI scripts, ad-hoc reports) must call
`run_pipeline()` so that the seed/history dedup is ALWAYS applied. This
prevents bugs where a quick script accidentally skips dedup and reports
keywords the user already targets.
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Callable

from core.seed_loader import load_seeds_by_country
from core.country_map import to_upup_country
from core.competitor_finder import find_competitors
from core.niche_validator import filter_by_jaccard
from core.keyword_scraper import get_keywords
from core.scorer import aggregate_keywords, classify
from core.dedup import exclude_seeds
from core.bidding_scraper import fetch_bidding_data
from core.snowball import find_relevant_bidders
from core.exporter import to_excel
from core.models import Competitor, ScoredKeyword


DEFAULT_USER_ID = "1789c9b1-73e7-4653-a6b7-01470694e825"
TOP_COMPETITORS = 15
SEEDS_FOR_SEARCH = 31
MAX_KEYWORDS_OUT = 200


def run_pipeline(
    adam_id: str,
    country_iso: str,
    output_path: str | Path,
    user_id: str = DEFAULT_USER_ID,
    record: bool = True,
    log: Callable[[str], None] = print,
) -> dict:
    """Run the full niche-finder pipeline and write an xlsx report.

    Always filters out keywords already in the user's seeds (campaigns) and
    keywords previously sent (history). Returns a stats dict so callers can
    build captions/messages.
    """
    log("Loading seeds...")
    grouped = load_seeds_by_country(adam_id, user_id)
    all_seeds = grouped.get(country_iso.upper(), [])
    if not all_seeds:
        raise RuntimeError(f"No seeds found for country {country_iso}")
    log(f"  {len(all_seeds)} seeds total for {country_iso}")

    upup_country = to_upup_country(country_iso)

    log("Finding competitors...")
    candidates = find_competitors(all_seeds[:SEEDS_FOR_SEARCH], country=upup_country)
    log(f"  {len(candidates)} candidates")

    log("Validating niche fit (Jaccard >= 30%)...")
    validated = filter_by_jaccard(candidates)[:TOP_COMPETITORS]
    for c in validated:
        c.validated = True
    log(f"  {len(validated)} validated")

    log("Scraping keywords per competitor (cached)...")
    for i, comp in enumerate(validated, 1):
        log(f"  [{i}/{len(validated)}] {comp.app_id}  {comp.name[:40]}")
        comp.keywords = get_keywords(comp.app_id, country=upup_country)

    log("Aggregating + filtering...")
    scored = aggregate_keywords(validated, allowed_languages=["EN", country_iso.upper()])
    total_before = len(scored)
    scored = exclude_seeds(scored, all_seeds)
    after_seeds = len(scored)
    log(f"  {total_before} → {after_seeds} (excl. seeds)")

    classified = classify(scored)
    log(f"  BEST {len(classified['BEST'])}, MEDIUM {len(classified['MEDIUM'])}, LOW {len(classified['TRASH'])}")

    log("Fetching real ASA bidder counts per keyword...")
    keywords_for_bidding = [k.name for k in scored if k.popularity and k.popularity >= 15]
    bidding_map = fetch_bidding_data(keywords_for_bidding, country=upup_country, log=log)
    for kw in scored:
        info = bidding_map.get(kw.name.lower().strip()) or {}
        kw.ad_count = info.get("bidding_apps_count")
        kw.bidder_ids = info.get("bidder_ids", [])
        if (kw.ad_count or 0) > 0:
            kw.source = "ASO+ASA"
        else:
            kw.source = "ASO"
    aso_asa_count = sum(1 for k in scored if k.source == "ASO+ASA")
    log(f"  enriched {len(keywords_for_bidding)} keywords; {aso_asa_count} have active ASA bidders")

    log("Snowball: finding relevant niche bidders to expand the pool...")
    existing_app_ids = {c.app_id for c in validated}
    extra_competitors = find_relevant_bidders(
        bidding_map=bidding_map,
        seed_keywords=all_seeds,
        country=upup_country,
        existing_app_ids=existing_app_ids,
        log=log,
    )

    if extra_competitors:
        validated_all = validated + extra_competitors
        log(f"  re-aggregating with {len(validated_all)} total competitors...")
        scored2 = aggregate_keywords(validated_all, allowed_languages=["EN", country_iso.upper()])
        total_before = len(scored2)
        scored2 = exclude_seeds(scored2, all_seeds)
        after_seeds = len(scored2)
        log(f"  {total_before} → {after_seeds} (excl. seeds)")

        for kw in scored2:
            info = bidding_map.get(kw.name.lower().strip()) or {}
            kw.ad_count = info.get("bidding_apps_count")
            if (kw.ad_count or 0) > 0:
                kw.source = "ASO+ASA"
            else:
                kw.source = "ASO"

        scored = scored2
        classified = classify(scored)
        validated = validated_all
        log(f"  BEST {len(classified['BEST'])}, MEDIUM {len(classified['MEDIUM'])}, LOW {len(classified['TRASH'])}")

    if len(scored) > MAX_KEYWORDS_OUT:
        log(f"Capping output to top {MAX_KEYWORDS_OUT} by score (had {len(scored)})")
        scored = sorted(scored, key=lambda k: k.score, reverse=True)[:MAX_KEYWORDS_OUT]
        classified = classify(scored)

    output_path = Path(output_path)
    to_excel(classified, validated, output_path, country=upup_country)
    log(f"Saved {output_path}")

    return {
        "output_path": output_path,
        "total_before": total_before,
        "excluded_seeds": total_before - after_seeds,
        "new_keywords": len(scored),
        "best": len(classified["BEST"]),
        "medium": len(classified["MEDIUM"]),
        "low": len(classified["TRASH"]),
        "validated_competitors": len(validated),
    }


def default_output_path(adam_id: str, country_iso: str, root: str | Path = "output") -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(root) / f"niche_{adam_id}_{country_iso}_{timestamp}.xlsx"
