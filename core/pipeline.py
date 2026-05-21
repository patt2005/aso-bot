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
from core.exporter import to_excel
from core.models import Competitor, ScoredKeyword


DEFAULT_USER_ID = "1789c9b1-73e7-4653-a6b7-01470694e825"
TOP_COMPETITORS = 15
SEEDS_FOR_SEARCH = 31
MAX_KEYWORDS_OUT = 100


def run_pipeline(
    adam_id: str,
    country_iso: str,
    output_path: str | Path,
    user_id: str = DEFAULT_USER_ID,
    log: Callable[[str], None] = print,
) -> dict:
    """Run the full niche-finder pipeline and write an xlsx report.

    Always filters out keywords already in the user's seeds (campaigns) and
    keywords previously sent (history). Returns a stats dict so callers can
    build captions/messages.
    """
    log("Loading seeds...")
    all_seeds = load_seeds_by_country(adam_id, user_id, country_iso.upper())
    if not all_seeds:
        raise RuntimeError(f"No seeds found for country {country_iso}")
    log(f"  {len(all_seeds)} seeds total for {country_iso}")

    upup_country = to_upup_country(country_iso)

    log("Finding competitors...")
    candidates, keyword_top_apps = find_competitors(all_seeds[:SEEDS_FOR_SEARCH], country=upup_country)
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
    scored = aggregate_keywords(validated, allowed_languages=["EN", country_iso.upper()], keyword_top_apps=keyword_top_apps)
    total_before = len(scored)
    scored = exclude_seeds(scored, all_seeds)
    after_seeds = len(scored)
    log(f"  {total_before} → {after_seeds} (excl. seeds)")

    if len(scored) > MAX_KEYWORDS_OUT:
        log(f"  Capping to top {MAX_KEYWORDS_OUT} by score (had {len(scored)})")
        scored = sorted(scored, key=lambda k: k.score, reverse=True)[:MAX_KEYWORDS_OUT]

    classified = classify(scored)
    log(f"  BEST {len(classified['BEST'])}, MEDIUM {len(classified['MEDIUM'])}, LOW {len(classified['TRASH'])}")

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
