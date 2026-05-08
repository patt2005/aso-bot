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
    ...
  }

We keep only ACTIVE + non-deleted entries. Group by countryCode so the
downstream pipeline can run a separate niche search per country.
"""
from __future__ import annotations
from collections import defaultdict
import httpx

from config import SEED_KEYWORDS_ENDPOINT


def _fetch_raw(adam_id: str | int, user_id: str) -> list[dict]:
    if not SEED_KEYWORDS_ENDPOINT:
        raise RuntimeError("SEED_KEYWORDS_ENDPOINT not configured in .env")
    resp = httpx.get(
        SEED_KEYWORDS_ENDPOINT,
        params={"adamId": str(adam_id), "userId": user_id},
        timeout=30.0,
    )
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, list):
        raise ValueError(f"expected list response, got {type(payload).__name__}")
    return payload


def load_seeds_by_country(adam_id: str | int, user_id: str) -> dict[str, list[str]]:
    """Return {country_code: [keyword, ...]} of active, non-deleted keywords."""
    raw = _fetch_raw(adam_id, user_id)
    grouped: dict[str, set[str]] = defaultdict(set)
    for item in raw:
        if item.get("deleted"):
            continue
        if item.get("status") != "ACTIVE":
            continue
        text = (item.get("text") or "").strip().lower()
        if not text:
            continue
        country = (item.get("countryCode") or "US").upper()
        grouped[country].add(text)
    return {country: sorted(words) for country, words in grouped.items()}


def load_seeds(adam_id: str | int, user_id: str, country_code: str | None = None) -> list[str]:
    """Convenience: return seeds for one country (or all merged if country_code is None)."""
    grouped = load_seeds_by_country(adam_id, user_id)
    if country_code:
        return grouped.get(country_code.upper(), [])
    merged: set[str] = set()
    for words in grouped.values():
        merged.update(words)
    return sorted(merged)
