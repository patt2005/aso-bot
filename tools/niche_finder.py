#!/usr/bin/env python3
"""App Store niche finder based on upup Top Free chart data.

Opens the upup rank page headlessly, captures the /pc/v1/rank POST response,
then scores each rising app by trend strength and niche openness.

Usage:
  python tools/niche_finder.py
  python tools/niche_finder.py --country 24 --min-incr 15 --top 20

Output: ranked table of niche opportunities printed to stdout.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import UPUP_AUTH_STATE  # noqa: E402
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DEFAULT_COUNTRY_ID = 24   # US
DEFAULT_MARKET_ID  = 1    # iOS App Store
DEVICE_ID          = 1    # iPhone
BRAND_ID_FREE      = 2    # Top Free
RANK_TYPE          = 1

# Niche scoring thresholds
INCR_EXPLOSIVE  = 100
INCR_STRONG     = 30
INCR_RISING     = 15
MAX_RANK        = 100     # only care about top 100
NEW_APP_DAYS    = 60      # app age considered "new"
CROWDED_REVIEWS = 10_000  # rating_count above this = established app


# ---------------------------------------------------------------------------
# Playwright helpers
# ---------------------------------------------------------------------------

def _make_rank_url(country_id: int, timestamp_ms: int | None = None) -> str:
    ts = timestamp_ms or (int(time.time()) * 1000)
    # upup URL pattern: /rank/ios/{market_id}-{brand_id}-{genre_id}-{country_id}-{sub}
    # genre_id 173 = All Categories, brand_id 2 = Top Free
    return f"https://www.upup.com/rank/ios/1-2-173-{country_id}-0?time={ts}&device={DEVICE_ID}"


def fetch_rank_data(country_id: int = DEFAULT_COUNTRY_ID) -> dict | None:
    """Open upup rank page in headless browser, capture the /rank POST response."""
    auth_state = str(ROOT / UPUP_AUTH_STATE.lstrip("./"))
    if not os.path.exists(UPUP_AUTH_STATE):
        # try relative to ROOT
        auth_state = str(ROOT / "cache" / "auth_state.json")

    url = _make_rank_url(country_id)
    captured: dict | None = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx_kwargs: dict = {"locale": "en-US"}
        if os.path.exists(auth_state):
            try:
                import json as _json
                _json.load(open(auth_state))
                ctx_kwargs["storage_state"] = auth_state
                print(f"[auth] Using saved session: {auth_state}")
            except Exception:
                print(f"[warn] Auth state at {auth_state} is corrupted — ignoring it")
                print("       Run: python tools/inspect_upup.py  to refresh the session")
        else:
            print(f"[warn] No auth state at {auth_state} — request may fail (401)")

        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()

        def on_response(resp):
            nonlocal captured
            if captured:
                return
            if "api.upup.com/pc/v1/rank" not in resp.url:
                return
            if resp.request.method != "POST":
                return
            try:
                body = resp.json()
                if body.get("code") == 0 and "data" in body:
                    captured = body["data"]
                    print(f"[ok] Captured /rank response ({len(body['data'].get('apps', []))} apps)")
            except Exception as e:
                print(f"[err] Failed to parse /rank response: {e}")

        page.on("response", on_response)
        print(f"[nav] Opening {url}")
        page.goto(url, wait_until="networkidle", timeout=30_000)

        # Wait up to 10s for the response to arrive after page load
        deadline = time.time() + 10
        while not captured and time.time() < deadline:
            time.sleep(0.3)

        browser.close()

    return captured


# ---------------------------------------------------------------------------
# Scoring logic
# ---------------------------------------------------------------------------

def score_app(rank_entry: dict, app_info: dict, now_ts: int) -> dict:
    """Combine rank movement + app quality into a niche score."""
    incr  = rank_entry.get("category_ranking_incr", 0)
    rank  = rank_entry.get("category_ranking", 999)
    is_ad = rank_entry.get("is_ad", 0)
    rtype = rank_entry.get("type", 0)   # 0=stable, 1=up, 2=down

    rating       = app_info.get("rating", 0)
    rating_count = app_info.get("rating_count", 0)
    release_ts   = app_info.get("release_time", 0)
    is_featured  = app_info.get("is_top_in_apps", 0)
    price        = app_info.get("price", 0)

    app_age_days = (now_ts - release_ts) / 86400 if release_ts else 9999

    # Base: rank velocity (positive only)
    velocity = max(incr, 0)

    # Penalty: Apple-promoted or featured → not organic
    organic_factor = 1.0 if (is_ad == 0 and is_featured == 0) else 0.4

    # Bonus: new app climbing = open niche
    newness_bonus = 1.5 if app_age_days <= NEW_APP_DAYS else 1.0

    # Bonus: low review count = not yet crowded
    openness_bonus = 1.3 if rating_count < CROWDED_REVIEWS else 1.0

    # Quality gate: bad rating = probably not a real trend
    quality = max(rating / 5.0, 0.1)

    niche_score = velocity * organic_factor * newness_bonus * openness_bonus * quality

    # Signal tier label
    if incr >= INCR_EXPLOSIVE:
        tier = "EXPLOSIVE"
    elif incr >= INCR_STRONG:
        tier = "STRONG"
    elif incr >= INCR_RISING:
        tier = "RISING"
    else:
        tier = "weak"

    return {
        "app_id":        app_info.get("app_id"),
        "name":          app_info.get("name", "Unknown"),
        "developer":     app_info.get("developer", {}).get("name", ""),
        "genre":         app_info.get("genres", [{}])[0].get("name", ""),
        "rank":          rank,
        "rank_incr":     incr,
        "type":          {0: "stable", 1: "rising", 2: "falling"}.get(rtype, "?"),
        "is_ad":         bool(is_ad),
        "is_featured":   bool(is_featured),
        "rating":        rating,
        "rating_count":  rating_count,
        "price":         price,
        "app_age_days":  round(app_age_days),
        "niche_score":   round(niche_score, 1),
        "tier":          tier,
        "release_date":  datetime.fromtimestamp(release_ts, tz=timezone.utc).strftime("%Y-%m-%d") if release_ts else "?",
    }


def find_niches(
    data: dict,
    min_incr: int = INCR_RISING,
    max_rank: int = MAX_RANK,
    top_n: int = 20,
    include_ads: bool = False,
) -> list[dict]:
    """Filter and score rising apps, return top niche opportunities."""
    apps_by_id = {a["id"]: a for a in data.get("apps", [])}
    now_ts = int(time.time())

    # Use brand_id=2 (Top Free) ranks — first entry in ranks list
    free_ranks = next(
        (r for r in data.get("ranks", []) if r.get("brand_id") == BRAND_ID_FREE),
        None,
    )
    if not free_ranks:
        print("[err] Could not find Top Free ranks in response")
        return []

    results = []
    for entry in free_ranks.get("apps", []):
        incr = entry.get("category_ranking_incr", 0)
        rank = entry.get("category_ranking", 999)
        is_ad = entry.get("is_ad", 0)

        # Filters
        if incr < min_incr:
            continue
        if rank > max_rank:
            continue
        if not include_ads and is_ad:
            continue

        app_id = entry.get("id")
        app_info = apps_by_id.get(app_id, {})
        scored = score_app(entry, app_info, now_ts)
        results.append(scored)

    results.sort(key=lambda x: x["niche_score"], reverse=True)
    return results[:top_n]


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

TIER_COLOR = {
    "EXPLOSIVE": "\033[91m",  # red
    "STRONG":    "\033[93m",  # yellow
    "RISING":    "\033[92m",  # green
    "weak":      "\033[90m",  # grey
}
RESET = "\033[0m"


def print_report(niches: list[dict]) -> None:
    if not niches:
        print("\nNo niche opportunities found with current filters.")
        return

    print(f"\n{'='*90}")
    print(f"  APP STORE NICHE FINDER  —  Top Free  —  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*90}")
    header = f"{'#':<3} {'Score':>6} {'Tier':<10} {'Rank':>5} {'Δ':>6}  {'Age':>5}  {'Reviews':>8}  {'★':>4}  {'Name'}"
    print(header)
    print("-" * 90)

    for i, n in enumerate(niches, 1):
        tier   = n["tier"]
        color  = TIER_COLOR.get(tier, "")
        badge  = f"[{tier}]"
        ad_tag = " [AD]" if n["is_ad"] else ""
        feat   = " [FEAT]" if n["is_featured"] else ""
        price  = f" ${n['price']:.2f}" if n["price"] else ""

        print(
            f"{i:<3} {color}{n['niche_score']:>6.1f} {badge:<10}{RESET} "
            f"#{n['rank']:<4} +{n['rank_incr']:<5}  "
            f"{n['app_age_days']:>4}d  "
            f"{n['rating_count']:>8,}  "
            f"{n['rating']:>4.1f}  "
            f"{n['name']}{ad_tag}{feat}{price}"
        )
        print(f"    └─ {n['developer']}  │  {n['genre']}  │  Released {n['release_date']}")

    print("="*90)
    print(f"\nLegend: Δ = rank positions gained  │  Age = days since release")
    print("Filters: is_ad=False  │  type=rising  │  rank_incr >= threshold")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="App Store niche finder via upup")
    parser.add_argument("--country", type=int, default=DEFAULT_COUNTRY_ID, help="Country ID (default: 24=US)")
    parser.add_argument("--min-incr", type=int, default=INCR_RISING, help=f"Minimum rank jump to consider (default: {INCR_RISING})")
    parser.add_argument("--max-rank", type=int, default=MAX_RANK, help=f"Maximum chart position to include (default: {MAX_RANK})")
    parser.add_argument("--top", type=int, default=20, help="How many results to show (default: 20)")
    parser.add_argument("--include-ads", action="store_true", help="Include Apple-promoted apps")
    parser.add_argument("--save", metavar="FILE", help="Save raw rank JSON to file")
    args = parser.parse_args()

    print(f"[start] Fetching Top Free chart for country_id={args.country}...")
    data = fetch_rank_data(country_id=args.country)

    if not data:
        print("[err] No data captured. Make sure you have a valid auth session.")
        print("      Run: python tools/inspect_upup.py  to create one.")
        sys.exit(1)

    if args.save:
        Path(args.save).write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"[save] Raw data saved to {args.save}")

    niches = find_niches(
        data,
        min_incr=args.min_incr,
        max_rank=args.max_rank,
        top_n=args.top,
        include_ads=args.include_ads,
    )

    print_report(niches)


if __name__ == "__main__":
    main()
