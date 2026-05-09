#!/usr/bin/env python3
"""Quick test for seed_loader against the real endpoint."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.seed_loader import load_seeds_by_country


def main():
    adam_id = sys.argv[1] if len(sys.argv) > 1 else "6746982805"
    user_id = sys.argv[2] if len(sys.argv) > 2 else "1789c9b1-73e7-4653-a6b7-01470694e825"

    print(f"Fetching seeds for adamId={adam_id} userId={user_id}")
    grouped = load_seeds_by_country(adam_id, user_id)
    for country, words in sorted(grouped.items()):
        print(f"\n{country} — {len(words)} keywords")
        for w in words:
            print(f"  - {w}")


if __name__ == "__main__":
    main()
