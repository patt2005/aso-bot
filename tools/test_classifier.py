from __future__ import annotations

import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import CACHE_DB_PATH, OPENAI_API_KEY
from core.keyword_classifier import (
    ClassifiedKeyword,
    _context_hash,
    classify_batch,
)

APP_CONTEXT = "iOS call recorder app, Romanian market"

EXPECTED = {
    "call recorder": {"core_niche"},
    "tapeacall": {"competitor_brand"},
    "record incoming whatsapp calls": {"long_tail_intent", "use_case"},
    "automatic recording": {"feature"},
    "phone": {"generic_term"},
    "asdfgh": {"irrelevant"},
}


def _count_cache_rows(ctx_hash: str) -> int:
    conn = sqlite3.connect(CACHE_DB_PATH)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM keyword_classification_cache WHERE app_context_hash = ?",
            (ctx_hash,),
        ).fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def _smoke_test_cache() -> None:
    from core.keyword_classifier import _cache_get, _cache_put

    ctx_hash = _context_hash("smoke-test-context")
    item = ClassifiedKeyword(
        name="smoke_test_kw",
        intent="core_niche",
        confidence=0.85,
        rationale="manual smoke test",
    )
    _cache_put(item, ctx_hash)
    fetched = _cache_get("smoke_test_kw", ctx_hash)
    assert fetched is not None, "cache put/get failed"
    assert fetched.name == "smoke_test_kw"
    assert fetched.intent == "core_niche"
    assert abs(fetched.confidence - 0.85) < 1e-6
    assert fetched.rationale == "manual smoke test"

    conn = sqlite3.connect(CACHE_DB_PATH)
    try:
        conn.execute(
            "DELETE FROM keyword_classification_cache "
            "WHERE keyword = ? AND app_context_hash = ?",
            ("smoke_test_kw", ctx_hash),
        )
        conn.commit()
    finally:
        conn.close()


def _print_table(results: list[ClassifiedKeyword]) -> None:
    width_kw = max(len("keyword"), max(len(r.name) for r in results))
    width_intent = max(len("intent"), max(len(r.intent) for r in results))
    header = f"{'keyword'.ljust(width_kw)}  {'intent'.ljust(width_intent)}  confidence"
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r.name.ljust(width_kw)}  {r.intent.ljust(width_intent)}  {r.confidence:.2f}"
        )


def main() -> None:
    _smoke_test_cache()

    if not OPENAI_API_KEY:
        print("OK (skipped GPT, no key)")
        return

    keywords = list(EXPECTED.keys())
    ctx_hash = _context_hash(APP_CONTEXT)

    conn = sqlite3.connect(CACHE_DB_PATH)
    try:
        placeholders = ",".join("?" * len(keywords))
        conn.execute(
            f"DELETE FROM keyword_classification_cache "
            f"WHERE app_context_hash = ? AND keyword IN ({placeholders})",
            (ctx_hash, *keywords),
        )
        conn.commit()
    finally:
        conn.close()

    rows_before = _count_cache_rows(ctx_hash)

    t0 = time.time()
    first = classify_batch(keywords, APP_CONTEXT)
    first_elapsed = time.time() - t0
    print(f"first call: {first_elapsed:.2f}s, {len(first)} results")
    _print_table(first)

    rows_after_first = _count_cache_rows(ctx_hash)
    populated = rows_after_first - rows_before
    print(f"cache rows added after first run: {populated}")

    failures: list[str] = []
    for r in first:
        expected = EXPECTED[r.name]
        if r.intent not in expected:
            failures.append(
                f"  {r.name!r} -> got {r.intent!r}, expected one of {sorted(expected)}"
            )
    if failures:
        print("intent class mismatches:")
        for line in failures:
            print(line)
        raise AssertionError("one or more keywords landed outside expected intent class")

    t1 = time.time()
    second = classify_batch(keywords, APP_CONTEXT)
    second_elapsed = time.time() - t1
    print(f"second call: {second_elapsed:.2f}s, {len(second)} results")

    rows_after_second = _count_cache_rows(ctx_hash)
    assert rows_after_second == rows_after_first, (
        "second run should not add new cache rows"
    )

    cache_hits = sum(
        1
        for kw in keywords
        if any(s.name == kw for s in second)
    )
    hit_rate = cache_hits / len(keywords)
    print(f"second-run cache hit rate: {hit_rate:.0%} ({cache_hits}/{len(keywords)})")

    assert second_elapsed < first_elapsed, (
        f"second call ({second_elapsed:.2f}s) not faster than first ({first_elapsed:.2f}s)"
    )

    print("OK")


if __name__ == "__main__":
    main()
