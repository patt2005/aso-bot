"""Load seed keywords from the Apple Search Ads keywords endpoint.

Endpoint:
  GET https://twebbackend-production.up.railway.app/api/keywords
       ?adamId={ios_app_id}&userId={uuid}

Response item shape:
  {
    "id": int, "campaignId": int, "adGroupId": int,
    "text": "phone call",                  # the keyword we care about
    "matchType": "EXACT",
    "bidAmount": {"amount": "1", "currency": "USD"},
    "status": "ACTIVE", "deleted": false,
    "countryCode": "RO",                   # per-keyword country
    "totalRevenue": 12.50,                 # revenue attributed to this keyword
    ...
  }

We keep only ACTIVE + non-deleted entries. Group by countryCode so the
downstream pipeline can run a separate niche search per country.
"""
from __future__ import annotations
from collections import defaultdict
import httpx

from config import SEED_KEYWORDS_ENDPOINT


def _fetch_raw(adam_id: str | int, user_id: str, country: str) -> list[dict]:
    if not SEED_KEYWORDS_ENDPOINT:
        raise RuntimeError("SEED_KEYWORDS_ENDPOINT not configured in .env")
    resp = httpx.get(
        SEED_KEYWORDS_ENDPOINT,
        params={"adamId": str(adam_id), "userId": user_id, "country": country},
        timeout=120.0,
    )
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, list):
        raise ValueError(f"expected list response, got {type(payload).__name__}")
    return payload


def load_seeds_by_country(adam_id: str | int, user_id: str, country: str) -> list[str]:
    """Return sorted list of active, non-deleted keywords for a single country."""
    raw = _fetch_raw(adam_id, user_id, country)
    words: set[str] = set()
    for item in raw:
        if item.get("deleted"):
            continue
        if item.get("status") != "ACTIVE":
            continue
        text = (item.get("text") or "").strip().lower()
        if not text:
            continue
        words.add(text)
    return sorted(words)


def load_seeds_with_revenue(
    adam_id: str | int,
    user_id: str,
    country_code: str,
) -> list[dict]:
    """Return active seeds with revenue data for a single country.

    Each item: { text: str, revenue: float }
    Multiple entries for the same keyword (e.g. different match types) are
    merged — revenue is summed, so you get the total attributed to that keyword.
    Sorted by revenue descending.
    """
    raw = _fetch_raw(adam_id, user_id, country_code)
    merged: dict[str, float] = defaultdict(float)

    for item in raw:
        if item.get("deleted"):
            continue
        if item.get("status") != "ACTIVE":
            continue
        text = (item.get("text") or "").strip().lower()
        if not text:
            continue
        revenue = float(item.get("totalRevenue") or 0)
        merged[text] += revenue

    return sorted(
        [{"text": kw, "revenue": rev} for kw, rev in merged.items()],
        key=lambda x: x["revenue"],
        reverse=True,
    )


def load_seeds(adam_id: str | int, user_id: str, country_code: str) -> list[str]:
    """Convenience wrapper: return seeds for a single country."""
    return load_seeds_by_country(adam_id, user_id, country_code)
