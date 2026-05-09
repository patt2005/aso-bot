"""Resolve an iOS adamId to the app's display name via iTunes Lookup API.

Public, unauthenticated endpoint. Cached in-process to avoid repeat calls
during a single pipeline run.
"""
from __future__ import annotations
import httpx


_NAME_CACHE: dict[str, str] = {}

LOOKUP_URL = "https://itunes.apple.com/lookup"


def get_app_name(adam_id: str | int, country: str = "us") -> str:
    """Return the trackName for the given adamId, or the id itself if lookup fails."""
    key = str(adam_id)
    if key in _NAME_CACHE:
        return _NAME_CACHE[key]

    try:
        resp = httpx.get(
            LOOKUP_URL,
            params={"id": key, "country": country.lower()},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results") or []
        name = (results[0].get("trackName") if results else "") or key
    except Exception:
        name = key

    _NAME_CACHE[key] = name
    return name
