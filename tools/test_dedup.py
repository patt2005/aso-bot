#!/usr/bin/env python3
"""Test that dedup excludes seeds and history correctly."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.models import ScoredKeyword
from core.dedup import (
    exclude_seeds,
    exclude_history,
    record_history,
    clear_history,
)


def make(name: str, score: float = 1.0) -> ScoredKeyword:
    return ScoredKeyword(
        name=name,
        popularity=10.0,
        avg_competitor_ranking=10.0,
        competitor_count=2,
        competitors=["app1", "app2"],
        score=score,
    )


def main():
    adam_id = "TEST_999"
    country_iso = "RO"
    clear_history(adam_id, country_iso)

    scored = [
        make("call recorder"),
        make("Call  Recorder"),
        make("inregistrare apel"),
        make("voice memos"),
        make("tape a call"),
        make("trapcall"),
    ]
    seeds = ["call recorder", "INREGISTRARE APEL", "phone call"]

    print(f"Input scored keywords: {len(scored)}")
    for s in scored:
        print(f"  - {s.name}")

    after_seeds = exclude_seeds(scored, seeds)
    print(f"\nAfter exclude_seeds (whitespace + case insensitive):")
    for s in after_seeds:
        print(f"  - {s.name}")

    from core.keyword_filter import normalize
    seed_names = {normalize(s) for s in seeds}
    for s in after_seeds:
        assert normalize(s.name) not in seed_names, f"{s.name} should be excluded"
    assert len(after_seeds) == 3, f"expected 3 after seed dedup, got {len(after_seeds)}"
    print("  ✓ seed exclusion works (case + whitespace insensitive)")

    print(f"\nRecording {len(after_seeds)} keywords in history...")
    n = record_history(after_seeds, adam_id, country_iso)
    print(f"  recorded {n} rows")

    after_history = exclude_history(after_seeds, adam_id, country_iso)
    print(f"\nAfter exclude_history (re-running same keywords):")
    print(f"  count = {len(after_history)}  (expected 0)")
    assert len(after_history) == 0, "all keywords should be filtered by history"
    print("  ✓ history exclusion works")

    new_keywords = [make("new keyword 1"), make("new keyword 2")]
    mixed = after_seeds + new_keywords
    after_history_mixed = exclude_history(mixed, adam_id, country_iso)
    print(f"\nMixed (4 in history + 2 new): after history filter = {len(after_history_mixed)}")
    assert len(after_history_mixed) == 2
    print("  ✓ only the 2 truly new keywords pass")

    clear_history(adam_id, country_iso)
    print("\nALL TESTS PASSED")


if __name__ == "__main__":
    main()
