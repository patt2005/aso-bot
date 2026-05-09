"""Self-contained smoke test for the advanced multi-factor keyword scorer.

Builds 4 fake validated competitors with handcrafted keywords designed to land
in distinct tiers (WINNERS, EASY_WINS, HIGH_VALUE, HIDDEN_GEMS, LOCAL_PLAYS,
AVOID), runs `score_advanced` and `classify_advanced`, then asserts each
keyword shows up in its expected tier(s).

Run:  python3 tools/test_advanced_scorer.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.models import Competitor, Keyword
from core.advanced_scorer import (
    AdvancedScoredKeyword,
    classify_advanced,
    score_advanced,
)


KW_WINNER = "call recorder"
KW_LONG_TAIL = "call recorder for iphone professional"
KW_BRAND = "tapeacall"
KW_LOCAL = "inregistrare apel"
KW_NOISE = "xyz random"


def _build_fake_competitors() -> list[Competitor]:
    winner_ranks = [3, 5, 4, 6]

    competitors: list[Competitor] = []
    for i in range(4):
        kws: list[Keyword] = [
            Keyword(name=KW_WINNER, ranking=winner_ranks[i], popularity=100.0),
        ]

        if i in (0, 1):
            kws.append(Keyword(
                name=KW_LONG_TAIL,
                ranking=12 if i == 0 else 15,
                popularity=22.0,
            ))

        if i in (0, 1):
            kws.append(Keyword(name=KW_LOCAL, ranking=20, popularity=20.0))

        if i == 0:
            kws.append(Keyword(name=KW_BRAND, ranking=1, popularity=100.0))
            kws.append(Keyword(name=KW_NOISE, ranking=80, popularity=5.0))

        kws.append(Keyword(name=f"filler kw c{i}", ranking=40 + i, popularity=12.0))
        kws.append(Keyword(name=f"another filler {i}", ranking=55 + i, popularity=8.0))

        competitors.append(Competitor(
            app_id=f"id-{2000 + i}",
            name=f"FakeCallApp {i}",
            category="Utilities",
            seed_overlap=0.5,
            matched_seeds=["call", "record"],
            validated=True,
            keywords=kws,
        ))

    return competitors


def _find(scored: list[AdvancedScoredKeyword], name: str) -> AdvancedScoredKeyword:
    for kw in scored:
        if kw.name == name.lower():
            return kw
    raise AssertionError(f"keyword {name!r} not found in scored output")


def _print_table(scored: list[AdvancedScoredKeyword]) -> None:
    header = (
        f"{'name':38s} {'pop':>5s} {'avg':>5s} {'min':>3s} {'max':>3s} "
        f"{'std':>5s} {'cnt':>3s} {'len':>9s} {'br':>2s} {'lc':>2s} "
        f"{'diff':>6s} {'opp':>6s} {'comp':>6s}  tiers"
    )
    print(header)
    print("-" * len(header))
    for kw in scored:
        print(
            f"{kw.name:38s} "
            f"{kw.popularity:5.1f} "
            f"{kw.avg_competitor_ranking:5.1f} "
            f"{kw.min_competitor_ranking:3d} "
            f"{kw.max_competitor_ranking:3d} "
            f"{kw.ranking_stddev:5.2f} "
            f"{kw.competitor_count:3d} "
            f"{kw.length_class:>9s} "
            f"{('Y' if kw.is_brand_keyword else '.'):>2s} "
            f"{('Y' if kw.is_local_language else '.'):>2s} "
            f"{kw.difficulty:6.3f} "
            f"{kw.opportunity:6.3f} "
            f"{kw.composite_score:6.3f}  "
            f"{','.join(kw.tiers) or '-'}"
        )


def main() -> int:
    competitors = _build_fake_competitors()
    print(f"[SETUP] built {len(competitors)} fake validated competitors")
    total = sum(len(c.keywords) for c in competitors)
    print(f"[SETUP] total keyword entries across competitors: {total}")

    scored = score_advanced(competitors, country_iso="RO")
    print(f"[SCORE] aggregated into {len(scored)} unique scored keywords\n")

    classified = classify_advanced(scored)

    print("[TIER COUNTS]")
    for tier_name, items in classified.items():
        print(f"  {tier_name:12s}: {len(items)}")
    print()

    print("[TABLE]")
    _print_table(scored)
    print()

    winner = _find(scored, KW_WINNER)
    long_tail = _find(scored, KW_LONG_TAIL)
    brand = _find(scored, KW_BRAND)
    local = _find(scored, KW_LOCAL)
    noise = _find(scored, KW_NOISE)

    assert "WINNERS" in winner.tiers, (
        f"{KW_WINNER!r} expected WINNERS, got {winner.tiers} (composite={winner.composite_score})"
    )
    assert "HIGH_VALUE" in winner.tiers, (
        f"{KW_WINNER!r} expected HIGH_VALUE, got {winner.tiers}"
    )

    assert "EASY_WINS" in long_tail.tiers, (
        f"{KW_LONG_TAIL!r} expected EASY_WINS, got {long_tail.tiers}"
    )
    assert "HIDDEN_GEMS" in long_tail.tiers, (
        f"{KW_LONG_TAIL!r} expected HIDDEN_GEMS, got {long_tail.tiers}"
    )
    assert long_tail.length_class == "long_tail", (
        f"{KW_LONG_TAIL!r} expected length_class long_tail, got {long_tail.length_class}"
    )

    assert brand.is_brand_keyword, f"{KW_BRAND!r} should be flagged is_brand_keyword"
    assert "EASY_WINS" in brand.tiers, (
        f"{KW_BRAND!r} expected EASY_WINS, got {brand.tiers} (opp={brand.opportunity})"
    )

    assert local.is_local_language, f"{KW_LOCAL!r} should be flagged is_local_language"
    assert "LOCAL_PLAYS" in local.tiers, (
        f"{KW_LOCAL!r} expected LOCAL_PLAYS, got {local.tiers}"
    )

    assert "AVOID" in noise.tiers, (
        f"{KW_NOISE!r} expected AVOID, got {noise.tiers}"
    )

    print("[OK] all assertions passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
