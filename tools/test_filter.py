from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.models import Competitor, Keyword
from core.scorer import aggregate_keywords


def main() -> int:
    keywords_a = [
        Keyword(name="call recorder", ranking=5, popularity=40.0),
        Keyword(name="call  recorder", ranking=7, popularity=42.0),
        Keyword(name="통화", ranking=10, popularity=30.0),
    ]
    keywords_b = [
        Keyword(name="perekam suara", ranking=12, popularity=25.0),
        Keyword(name="inregistrare apel", ranking=8, popularity=35.0),
    ]

    competitors = [
        Competitor(app_id="id-1", name="FakeCallApp", validated=True, keywords=keywords_a),
        Competitor(app_id="id-2", name="FakeCallApp2", validated=True, keywords=keywords_b),
    ]

    scored = aggregate_keywords(competitors, allowed_languages=["EN", "RO"])
    names = [s.name for s in scored]

    print("[RESULT] scored keywords:")
    for s in scored:
        print(f"  - {s.name!r} pop={s.popularity} comps={s.competitor_count} score={s.score}")

    assert "통화" not in names, "Korean keyword should be filtered out"
    assert "perekam suara" not in names, "Indonesian keyword should be filtered out"
    assert "call recorder" in names, "expected 'call recorder' in results"
    assert names.count("call recorder") == 1, "whitespace dedup failed: 'call recorder' appears more than once"
    assert "inregistrare apel" in names, "expected 'inregistrare apel' in results"
    assert len(scored) == 2, f"expected exactly 2 unique keywords, got {len(scored)}: {names}"

    call_rec = next(s for s in scored if s.name == "call recorder")
    assert call_rec.competitor_count == 1, f"expected competitor_count=1 for 'call recorder', got {call_rec.competitor_count}"
    assert len(call_rec.competitors) == 1 and call_rec.competitors[0] == "id-1"

    print("\n[OK] all assertions passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
