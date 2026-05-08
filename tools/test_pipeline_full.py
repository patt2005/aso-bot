#!/usr/bin/env python3
"""Full end-to-end pipeline test: seeds -> competitors -> validate -> scrape -> score -> xlsx.

No Telegram send (verify file locally first).
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.seed_loader import load_seeds_by_country
from core.competitor_finder import find_competitors
from core.niche_validator import filter_by_jaccard
from core.keyword_scraper import get_keywords
from core.scorer import aggregate_keywords, classify
from core.exporter import to_excel
from core.country_map import to_upup_country


def main():
    adam_id = "6746982805"
    user_id = "1789c9b1-73e7-4653-a6b7-01470694e825"

    t0 = time.time()
    print("STEP 1 — fetch seeds")
    grouped = load_seeds_by_country(adam_id, user_id)
    ro_seeds = grouped.get("RO", [])[:8]
    print(f"  {len(ro_seeds)} RO seeds (capped to 8 for speed)")

    print("\nSTEP 2 — find competitors")
    upup_country = to_upup_country("RO")
    candidates = find_competitors(ro_seeds, country=upup_country)
    print(f"  {len(candidates)} candidates")

    print("\nSTEP 3 — Jaccard filter")
    validated = filter_by_jaccard(candidates)
    for c in validated:
        c.validated = True
    validated = validated[:8]
    print(f"  {len(validated)} validated (capped to 8)")

    print("\nSTEP 4 — scrape keywords per competitor")
    for i, comp in enumerate(validated, 1):
        print(f"  [{i}/{len(validated)}] {comp.app_id}  {comp.name[:40]}")
        comp.keywords = get_keywords(comp.app_id, country=upup_country)
        print(f"    -> {len(comp.keywords)} keywords")

    print("\nSTEP 5 — score + classify")
    scored = aggregate_keywords(validated)
    classified = classify(scored)
    print(
        f"  BEST: {len(classified['BEST'])}, "
        f"MEDIUM: {len(classified['MEDIUM'])}, "
        f"TRASH: {len(classified['TRASH'])}"
    )

    print("\nSTEP 6 — export xlsx")
    out_path = Path("output") / f"niche_RO_{adam_id}.xlsx"
    to_excel(classified, validated, out_path)
    print(f"  written -> {out_path}")

    elapsed = time.time() - t0
    print(f"\nTotal: {elapsed:.1f}s")

    print("\nTop 10 BEST keywords:")
    for kw in classified["BEST"][:10]:
        print(f"  {kw.score:>7.2f}  pop={kw.popularity:>5}  comps={kw.competitor_count}  {kw.name}")
    print("\nTop 5 MEDIUM keywords:")
    for kw in classified["MEDIUM"][:5]:
        print(f"  {kw.score:>7.2f}  pop={kw.popularity:>5}  comps={kw.competitor_count}  {kw.name}")


if __name__ == "__main__":
    main()
