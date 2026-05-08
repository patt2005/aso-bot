#!/usr/bin/env python3
"""Sanity test for core.gap_analysis."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.models import Keyword, Competitor
from core.gap_analysis import find_gap_keywords, find_owned_keywords, summarize


def main() -> int:
    our_keywords = [
        Keyword(name="call recorder", ranking=5, popularity=50),
        Keyword(name="phone recorder", ranking=80, popularity=30),
        Keyword(name="record calls", ranking=18, popularity=22),
        Keyword(name="audio recorder", ranking=45, popularity=20),
        Keyword(name="meeting notes", ranking=None, popularity=10),
    ]

    comp_a = Competitor(
        app_id="app.a",
        name="Comp A",
        validated=True,
        keywords=[
            Keyword(name="voice memos", ranking=7, popularity=40),
            Keyword(name="tape a call", ranking=10, popularity=25),
            Keyword(name="phone recorder", ranking=12, popularity=30),
            Keyword(name="truecaller", ranking=22, popularity=35),
            Keyword(name="solo unique a", ranking=4, popularity=28),
        ],
    )
    comp_b = Competitor(
        app_id="app.b",
        name="Comp B",
        validated=True,
        keywords=[
            Keyword(name="voice memos", ranking=9, popularity=38),
            Keyword(name="tape a call", ranking=14, popularity=24),
            Keyword(name="phone recorder", ranking=18, popularity=28),
            Keyword(name="call recorder", ranking=11, popularity=50),
            Keyword(name="solo unique b", ranking=6, popularity=33),
        ],
    )
    comp_c = Competitor(
        app_id="app.c",
        name="Comp C",
        validated=True,
        keywords=[
            Keyword(name="voice memos", ranking=8, popularity=40),
            Keyword(name="truecaller", ranking=25, popularity=35),
            Keyword(name="call recorder", ranking=9, popularity=50),
            Keyword(name="solo unique c", ranking=3, popularity=29),
            Keyword(name="low pop word", ranking=4, popularity=5),
            Keyword(name="low pop word two", ranking=2, popularity=6),
        ],
    )

    competitors = [comp_a, comp_b, comp_c]

    gaps = find_gap_keywords(our_keywords, competitors)
    gap_names = {g.name.lower() for g in gaps}

    assert "voice memos" in gap_names, f"expected 'voice memos' in gaps: {gap_names}"
    assert "tape a call" in gap_names, f"expected 'tape a call' in gaps: {gap_names}"
    assert "call recorder" not in gap_names, f"'call recorder' should NOT be a gap: {gap_names}"
    assert "phone recorder" in gap_names, f"'phone recorder' should be a gap (we rank 80): {gap_names}"

    # Single-competitor keywords must be excluded.
    for solo in ("solo unique a", "solo unique b", "solo unique c"):
        assert solo not in gap_names, f"{solo} appeared on only one competitor and should be filtered"

    owned = find_owned_keywords(our_keywords)
    owned_names = {k.name.lower() for k in owned}
    assert "call recorder" in owned_names, f"'call recorder' (rank 5) should be owned: {owned_names}"
    assert "phone recorder" not in owned_names, f"'phone recorder' (rank 80) should NOT be owned: {owned_names}"
    assert "record calls" in owned_names, f"'record calls' (rank 18) should be owned: {owned_names}"
    assert "audio recorder" not in owned_names, f"'audio recorder' (rank 45) should NOT be owned: {owned_names}"

    print(summarize(gaps, owned))
    print("\nAll assertions passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
