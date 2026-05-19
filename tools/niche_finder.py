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
    captured_token: str | None = None

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
            before = len(page_responses)
            page_obj.keyboard.press("End")
            print(f"[scroll] End key press #{pg}")
            deadline = time.time() + 8
            while len(page_responses) <= before and time.time() < deadline:
                time.sleep(0.3)
            if len(page_responses) <= before:
                print(f"[warn] Page {pg + 1} did not arrive — stopping")
                break

        browser.close()

    if not page_responses:
        return None

    # Merge all pages into a single structure
    all_apps: dict[str, dict] = {}
    free_rank_entries: list[dict] = []
    free_brand_meta: dict = {}

    for i, data in enumerate(page_responses):
        for app in data.get("apps", []):
            all_apps[app["id"]] = app
        ranks = data.get("ranks") or []
        if ranks:
            if not free_brand_meta:
                free_brand_meta = {k: v for k, v in ranks[0].items() if k != "apps"}
            free_rank_entries.extend(ranks[0].get("apps", []))

    print(f"[summary] {len(free_rank_entries)} Top Free rank entries, "
          f"{len(all_apps)} app detail records across {len(page_responses)} pages")

    return {
        "apps":   list(all_apps.values()),
        "ranks":  [{**free_brand_meta, "apps": free_rank_entries}],
        "_token": captured_token,
    }


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
    max_age_days: int = 120,
    top_n: int = 20,
    include_ads: bool = False,
) -> list[dict]:
    """Filter and score rising apps, return top niche opportunities.

    Uses ranks[0] (Top Free, brand_id=2) — which is pre-merged across all
    paginated pages by fetch_rank_data(). App details come from apps[] which
    is also pre-merged across pages, so no separate batch API call is needed.
    """
    apps_by_id = {a["id"]: a for a in data.get("apps", [])}
    now_ts = int(time.time())

    # ranks[0] is always Top Free (brand_id=2)
    ranks_list = data.get("ranks") or []
    if not ranks_list:
        print("[err] No ranks in response")
        return []
    free_ranks = ranks_list[0]
    all_entries = free_ranks.get("apps", [])
    print(f"[info] Using ranks[0]: brand_id={free_ranks.get('brand_id')}, "
          f"{len(all_entries)} total rank entries, {len(apps_by_id)} app detail records")

    results = []
    missing = 0
    for entry in all_entries:
        incr  = entry.get("category_ranking_incr", 0)
        rank  = entry.get("category_ranking", 999)
        is_ad = entry.get("is_ad", 0)

        if incr < min_incr:
            continue
        if rank > max_rank:
            continue
        if not include_ads and is_ad:
            continue

        upup_id  = entry.get("id")
        app_info = apps_by_id.get(upup_id, {})
        if not app_info:
            missing += 1

        scored = score_app(entry, app_info, now_ts)

        if max_age_days and scored["app_age_days"] > max_age_days:
            continue

        results.append(scored)

    if missing:
        print(f"[warn] {missing} rank entries had no matching app detail record")

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
