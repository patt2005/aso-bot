from __future__ import annotations
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.keyword_scraper import get_keywords

APP_ID = "ygguvu633kd1dt6"
COUNTRY = 25


def main() -> None:
    t0 = time.time()
    first = get_keywords(APP_ID, COUNTRY)
    first_elapsed = time.time() - t0
    print(f"first call: {first_elapsed:.2f}s, {len(first)} keywords")

    t1 = time.time()
    second = get_keywords(APP_ID, COUNTRY)
    second_elapsed = time.time() - t1
    print(f"second call: {second_elapsed:.2f}s, {len(second)} keywords")

    first_names = [k.name for k in first]
    second_names = [k.name for k in second]
    assert first_names == second_names, "cached keywords differ from scraped keywords"

    speedup = first_elapsed / max(second_elapsed, 1e-6)
    print(f"speedup: {speedup:.1f}x")
    assert second_elapsed * 5 <= first_elapsed, (
        f"second call not at least 5x faster: first={first_elapsed:.2f}s "
        f"second={second_elapsed:.2f}s"
    )

    print("OK")


if __name__ == "__main__":
    main()
