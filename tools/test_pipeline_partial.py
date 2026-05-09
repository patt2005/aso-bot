#!/usr/bin/env python3
"""Run seed_loader + competitor_finder against real Romanian seeds.

Stops short of keyword scraping (slow). Verifies:
  - we can pull seeds from the endpoint
  - we can find competitors for them on upup with country=RO
  - Jaccard validation produces a reasonable shortlist
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.seed_loader import load_seeds_by_country
from core.competitor_finder import find_competitors
from core.niche_validator import filter_by_jaccard
from core.country_map import to_upup_country


def main():
    adam_id = "6746982805"
    user_id = "1789c9b1-73e7-4653-a6b7-01470694e825"

    print("=" * 60)
    print("STEP 1 — fetching seeds")
    print("=" * 60)
    grouped = load_seeds_by_country(adam_id, user_id)
    for country, words in grouped.items():
        print(f"  {country}: {len(words)} seeds")

    if "RO" not in grouped:
        print("\nNo RO seeds — aborting")
        return
    ro_seeds = grouped["RO"]

    SEEDS_TO_USE = ro_seeds[:8]  # cap to keep test fast
    print(f"\nUsing first {len(SEEDS_TO_USE)} seeds for the demo:")
    for s in SEEDS_TO_USE:
        print(f"  - {s}")

    print("\n" + "=" * 60)
    print("STEP 2 — finding competitors on upup")
    print("=" * 60)
    upup_country = to_upup_country("RO")
    print(f"upup country_id = {upup_country}")

    candidates = find_competitors(SEEDS_TO_USE, country=upup_country)
    print(f"\n{len(candidates)} candidate competitors total\n")
    for c in candidates[:20]:
        print(f"  {c.seed_overlap:>5.0%}  {c.app_id:18s}  {c.name[:45]}")

    print("\n" + "=" * 60)
    print("STEP 3 — Jaccard filter (>= 30% overlap)")
    print("=" * 60)
    validated = filter_by_jaccard(candidates)
    print(f"\n{len(validated)} survived Jaccard filter\n")
    for c in validated:
        print(f"  {c.seed_overlap:>5.0%}  {c.app_id:18s}  {c.name[:45]}")
        print(f"         seeds matched: {', '.join(c.matched_seeds)}")


if __name__ == "__main__":
    main()
