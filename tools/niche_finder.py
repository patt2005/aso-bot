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
    return f"https://www.upup.com/rank/ios/1-1-173-{country_id}-0?time={ts}&device={DEVICE_ID}"


def _load_auth_state(auth_state: str) -> dict | None:
    """Load and validate auth state JSON. Returns None if missing or corrupt."""
    if not os.path.exists(auth_state):
        return None
    try:
        with open(auth_state) as f:
            return json.load(f)
    except Exception:
        return None


def fetch_rank_data(country_id: int = DEFAULT_COUNTRY_ID, pages: int = 4) -> dict | None:
    """Open upup rank page in headless browser, auto-scroll to trigger all rank pages,
    then merge their responses.

    The page uses infinite scroll — each scroll fires a new POST /pc/v1/rank for the
    next 20 entries. We scroll {pages} times to collect pages 1-{pages} (ranks 1-80).

    Returns a merged dict:
      - apps[]  : all app detail objects from all pages, deduped by id
      - ranks[] : single entry whose apps[] = all Top Free rank entries in order
      - _token  : the captured Bearer token
    """
    auth_state_path = str(ROOT / UPUP_AUTH_STATE.lstrip("./"))
    if not os.path.exists(auth_state_path):
        auth_state_path = str(ROOT / "cache" / "auth_state.json")

    url = _make_rank_url(country_id)
    auth_data = _load_auth_state(auth_state_path)

    page_responses: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx_kwargs: dict = {"locale": "en-US"}
        if auth_data:
            ctx_kwargs["storage_state"] = auth_state_path
            print(f"[auth] Using saved session: {auth_state_path}")
        else:
            print(f"[warn] No valid auth state at {auth_state_path} — request may fail")
            print("       Run: python tools/inspect_upup.py  to refresh the session")

        context = browser.new_context(**ctx_kwargs)
        page_obj = context.new_page()

        def on_response(r):
            try:
                if "api.upup.com/pc/v1/rank" in r.url and r.request.method == "POST":
                    rb = r.json()
                    if rb.get("code") == 0 and "data" in rb:
                        rd = rb["data"]
                        pg_num   = len(page_responses) + 1
                        ra_apps  = len(rd.get("apps", []))
                        ra_ranks = len((rd.get("ranks") or [{}])[0].get("apps", []))
                        print(f"[ok] Page {pg_num} captured — {ra_apps} app details, {ra_ranks} rank entries")
                        page_responses.append(rd)

            except Exception as exc:
                print(f"[err] Response handler: {exc}")

        page_obj.on("response", on_response)
        print(f"[nav] Opening {url}")
        page_obj.goto(url, wait_until="networkidle", timeout=30_000)

        for pg in range(1, pages + 1):
            page_obj.keyboard.press("End")
            print(f"[scroll] End key press #{pg}")
            time.sleep(1)

        browser.close()

    if not page_responses:
        return None

    free_rank_entries: list[dict] = []
    apps_dict = {}

    for data in page_responses:
        top_free_ranks = data["ranks"][0].get("apps", [])

        for app in data.get("apps", []):
            apps_dict[app["id"]] = app

        for rank in top_free_ranks:
            app_id = rank.get("id")
            app = apps_dict[app_id]
            if app is not None:
                app["total_ranking"] = rank.get("total_ranking", 0)
                app["total_ranking_incr"] = rank.get("total_ranking_incr", 0)
                app["is_ad"] = rank.get("is_ad", 0)
                app["category_id"] = rank.get("category_id", 0)
                free_rank_entries.append(app)

    print(f"Found {len(free_rank_entries)} apps")

    return {
        "apps": free_rank_entries,
    }


# ---------------------------------------------------------------------------
# Scoring logic
# ---------------------------------------------------------------------------

def score_app(app: dict, now_ts: int) -> dict:
    """Combine rank movement + app quality into a niche score."""
    incr  = app.get("total_ranking_incr", 0)
    rank  = app.get("total_ranking", 999)
    is_ad = app.get("is_ad", 0)

    rating       = app.get("rating", 0)
    rating_count = app.get("rating_count", 0)
    release_ts   = app.get("release_time", 0)
    is_featured  = app.get("is_top_in_apps", 0)
    price        = app.get("price", 0)

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
        "app_id":        app.get("app_id"),
        "name":          app.get("name", "Unknown"),
        "developer":     app.get("developer", {}).get("name", ""),
        "genre":         app.get("genres", [{}])[0].get("name", ""),
        "rank":          rank,
        "rank_incr":     incr,
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
    max_age_days: int = 120,
    top_n: int = 20,
    include_ads: bool = False,
) -> list[dict]:
    """Filter and score rising apps, return top niche opportunities.

    Expects data["apps"] to be a flat list of app objects, each already
    containing total_ranking, total_ranking_incr, and is_ad fields as
    produced by fetch_rank_data().
    """
    all_apps = data.get("apps", [])
    now_ts = int(time.time())

    print(f"[info] Scoring {len(all_apps)} apps from flat apps[] list")

    results = []
    for app in all_apps:
        incr  = app.get("total_ranking_incr", 0)
        rank  = app.get("total_ranking", 999)
        is_ad = app.get("is_ad", 0)

        if incr < min_incr:
            continue
        if rank > max_rank:
            continue
        if not include_ads and is_ad:
            continue

        scored = score_app(app, now_ts)

        if max_age_days and scored["app_age_days"] > max_age_days:
            continue

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
    parser.add_argument("--max-age", type=int, default=120, help="Maximum app age in days to include (default: 120)")
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
        max_age_days=args.max_age,
        top_n=args.top,
        include_ads=args.include_ads,
    )

    print_report(niches)


if __name__ == "__main__":
    main()
