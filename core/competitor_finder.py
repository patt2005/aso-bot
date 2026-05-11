"""Find competitor apps that rank for a given list of seed keywords.

Uses the upup search endpoint (discovered via headful inspection):
    GET /pc/v2/word/search_related_contents
        ?market_type=1&country_id=24&word=<keyword>&k=<session_token>

The `k` parameter is a session-bound token computed in upup's JS, so we cannot
call the API directly. Instead we navigate the upup page, type the keyword in
the search input, and listen for the search XHR response.

Aggregates results across all seeds — each app's seed_overlap = how many of
the seed keywords it shows up for.
"""
from __future__ import annotations
import json
import os
from collections import defaultdict
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

from core.models import Competitor
from config import UPUP_AUTH_STATE, DEFAULT_MARKET


SEARCH_API_FRAGMENT = "/pc/v2/word/search_related_contents"
HOME_URL = "https://www.upup.com/"


def find_competitors(
    seed_keywords: list[str],
    country: int,
    market: int = DEFAULT_MARKET,
    headless: bool = True,
) -> tuple[list[Competitor], dict[str, list[tuple[str, int]]]]:
    """For each seed keyword, query upup search and collect candidate apps.

    Returns:
        competitors: ordered by seed_overlap (descending)
        keyword_top_apps: keyword → list of (app_name, rank_position) for top 5
    """
    overlap: dict[str, set[str]] = defaultdict(set)
    metadata: dict[str, dict] = {}
    keyword_top_apps: dict[str, list[tuple[str, int]]] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx_kwargs: dict = {"locale": "en-US"}
        if os.path.exists(UPUP_AUTH_STATE):
            ctx_kwargs["storage_state"] = UPUP_AUTH_STATE
        context = browser.new_context(**ctx_kwargs)

        # upup persists selected country/market in localStorage. Force them so
        # the search call returns results for the country we want.
        context.add_init_script(
            f"""
            try {{
                localStorage.setItem('country', '{country}');
                localStorage.setItem('market', '{market}');
            }} catch (e) {{}}
            """
        )

        page = context.new_page()

        current_seed: dict = {"value": ""}

        def on_response(resp):
            try:
                if resp.request.resource_type not in ("xhr", "fetch"):
                    return
                if SEARCH_API_FRAGMENT not in resp.url:
                    return
                if "application/json" not in resp.headers.get("content-type", "").lower():
                    return

                payload = resp.json()
                data = payload.get("data") or {}
                app_list = data.get("app_list") or []
                seed = current_seed["value"]

                top5 = []
                for rank_pos, app in enumerate(app_list, 1):
                    upup_id = app.get("id")
                    if not upup_id:
                        continue
                    overlap[upup_id].add(seed)
                    if upup_id not in metadata:
                        genres = app.get("genres") or []
                        category = ""
                        if genres and isinstance(genres, list) and genres[0].get("name"):
                            category = genres[0]["name"]
                        metadata[upup_id] = {
                            "name": app.get("name", ""),
                            "category": category,
                            "ios_app_id": app.get("app_id"),
                            "bundle_id": app.get("bundle_id", ""),
                        }
                    if rank_pos <= 5:
                        top5.append((app.get("name", upup_id), rank_pos))
                if seed and top5:
                    keyword_top_apps[seed] = top5
            except Exception:
                pass

        page.on("response", on_response)
        page.set_default_navigation_timeout(60_000)

        try:
            page.goto(HOME_URL, wait_until="domcontentloaded")
        except PWTimeoutError:
            pass
        page.wait_for_timeout(3000)

        for i, seed in enumerate(seed_keywords, 1):
            current_seed["value"] = seed
            try:
                _trigger_search(page, seed, country, market)
                page.wait_for_timeout(2500)
            except Exception as exc:
                print(f"  ! search failed for {seed!r}: {exc} — reloading home")
                try:
                    page.goto(HOME_URL, wait_until="domcontentloaded")
                    page.wait_for_timeout(2500)
                    _trigger_search(page, seed, country, market)
                    page.wait_for_timeout(2500)
                except Exception as exc2:
                    print(f"  ! retry failed for {seed!r}: {exc2}")
            if i % 8 == 0 and i < len(seed_keywords):
                try:
                    page.goto(HOME_URL, wait_until="domcontentloaded")
                    page.wait_for_timeout(2000)
                except Exception:
                    pass
            if i % 5 == 0:
                print(f"  [{i}/{len(seed_keywords)}] searched, {len(overlap)} unique apps so far")

        browser.close()

    competitors = []
    total_seeds = max(len(seed_keywords), 1)
    for app_id, seeds in overlap.items():
        meta = metadata.get(app_id, {})
        competitors.append(Competitor(
            app_id=app_id,
            name=meta.get("name", ""),
            category=meta.get("category", ""),
            seed_overlap=len(seeds) / total_seeds,
            matched_seeds=sorted(seeds),
        ))
    competitors.sort(key=lambda c: c.seed_overlap, reverse=True)
    return competitors, keyword_top_apps


def _trigger_search(page, keyword: str, country: int, market: int) -> None:
    """Type keyword into upup search input to trigger search_related_contents XHR."""
    selectors = [
        'input[placeholder*="search" i]',
        'input[placeholder*="Search" i]',
        'input[type="search"]',
        'input.ant-input',
        'input',
    ]
    last_err = None
    for sel in selectors:
        try:
            el = page.locator(sel).first
            count = page.locator(sel).count()
            if count == 0:
                continue
            print(f"  [debug] trying selector {sel!r} ({count} matches)")
            el.click(timeout=3000)
            el.fill("")
            el.type(keyword, delay=60)
            print(f"  [debug] typed {keyword!r} into {sel!r}")
            return
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"could not locate search input on upup ({last_err})")
