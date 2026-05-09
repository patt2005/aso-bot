#!/usr/bin/env python3
"""Quick test for competitor_finder.find_competitors.

Runs a single seed keyword through the upup search and prints the result.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.competitor_finder import find_competitors


def main():
    seed = sys.argv[1] if len(sys.argv) > 1 else "call recorder"
    country = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    headless = "--headful" not in sys.argv

    print(f"Searching: {seed!r} (country={country}, headless={headless})")
    competitors = find_competitors([seed], country=country, headless=headless)
    print(f"\nFound {len(competitors)} competitors:")
    for c in competitors[:20]:
        print(f"  {c.seed_overlap:.0%}  {c.app_id:20s}  {c.category:25s}  {c.name}")


if __name__ == "__main__":
    main()
