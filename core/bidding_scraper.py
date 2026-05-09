"""Fetch the actual ASA bidder count for a list of keywords.

Endpoint:
  GET /pc/v1/word/app_bidding
       ?market_id=1&country_id=25&word=<keyword>&device_id=1
       &start_time=<unix>&end_time=<unix>

Response shape:
  data.word.bidding_apps_count  → integer (the real bidder count)
  data.list                     → list of bidding apps with their stats

We open ONE Playwright context and reuse it for all keywords (much faster than
re-launching browser per keyword). Results are cached in SQLite for 24h.
"""
from __future__ import annotations
import json
import os
import sqlite3
import time
from pathlib import Path
from urllib.parse import quote
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

from config import UPUP_AUTH_STATE, CACHE_DB_PATH


BIDDING_FRAGMENT = "/pc/v1/word/app_bidding"
BIDDING_TABLE = "keyword_bidding_cache"
BIDDING_TTL_HOURS = 24


def _conn() -> sqlite3.Connection:
    Path(CACHE_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CACHE_DB_PATH)
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {BIDDING_TABLE} (
            keyword TEXT NOT NULL,
            country INTEGER NOT NULL,
            market INTEGER NOT NULL,
            scraped_at REAL NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (keyword, country, market)
        )
        """
    )
    return conn


def _get_cached(word: str, country: int, market: int) -> dict | None:
    cutoff = time.time() - BIDDING_TTL_HOURS * 3600
    with _conn() as conn:
        row = conn.execute(
            f"SELECT payload_json, scraped_at FROM {BIDDING_TABLE} "
            f"WHERE keyword=? AND country=? AND market=?",
            (word, country, market),
        ).fetchone()
    if not row:
        return None
    payload_json, scraped_at = row
    if scraped_at < cutoff:
        return None
    return json.loads(payload_json)


def _set_cached(word: str, country: int, market: int, payload: dict) -> None:
    with _conn() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO {BIDDING_TABLE} "
            f"(keyword, country, market, scraped_at, payload_json) VALUES (?,?,?,?,?)",
            (word, country, market, time.time(), json.dumps(payload, ensure_ascii=False)),
        )
        conn.commit()


def fetch_bidding_data(
    keywords: list[str],
    country: int,
    market: int = 1,
    headless: bool = True,
    use_cache: bool = True,
    log=print,
) -> dict[str, dict]:
    """For each keyword return {bidding_apps_count, top_bidders: [name, ...]}.

    Reuses a single Playwright browser/context across all keywords.
    Returns dict keyed by keyword (lowercased).
    """
    results: dict[str, dict] = {}
    to_fetch: list[str] = []

    for word in keywords:
        key = word.lower().strip()
        if not key:
            continue
        if use_cache:
            cached = _get_cached(key, country, market)
            if cached is not None:
                results[key] = cached
                continue
        to_fetch.append(key)

    if not to_fetch:
        return results

    log(f"  fetching bidding data for {len(to_fetch)} keywords (cached: {len(results)})")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx_kwargs = {"locale": "en-US"}
        if os.path.exists(UPUP_AUTH_STATE):
            ctx_kwargs["storage_state"] = UPUP_AUTH_STATE
        context = browser.new_context(**ctx_kwargs)
        context.add_init_script(
            f"localStorage.setItem('country','{country}'); localStorage.setItem('market','{market}');"
        )
        page = context.new_page()
        page.set_default_navigation_timeout(45_000)

        current = {"word": ""}

        def on_response(resp):
            try:
                if BIDDING_FRAGMENT not in resp.url:
                    return
                if "application/json" not in resp.headers.get("content-type", "").lower():
                    return
                payload = resp.json()
                data = payload.get("data") or {}
                word_info = data.get("word") or {}
                bidding_list = data.get("list") or []
                top_bidders = []
                bidder_ids = []
                for item in bidding_list[:10]:
                    app = item.get("app") or {}
                    if app.get("name"):
                        top_bidders.append(app["name"])
                    if app.get("id"):
                        bidder_ids.append(app["id"])
                summary = {
                    "bidding_apps_count": word_info.get("bidding_apps_count", 0),
                    "popularity": word_info.get("popularity"),
                    "results_count": word_info.get("results_count"),
                    "top_bidders": top_bidders,
                    "bidder_ids": bidder_ids,
                }
                results[current["word"]] = summary
                _set_cached(current["word"], country, market, summary)
            except Exception:
                pass

        page.on("response", on_response)

        for i, word in enumerate(to_fetch, 1):
            current["word"] = word
            url = f"https://www.upup.com/search/ios-1-4-1-{country}-1-{quote(word)}?time=&device=1"
            try:
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(4500)
            except PWTimeoutError:
                pass
            if word not in results:
                _set_cached(word, country, market, {"bidding_apps_count": 0, "top_bidders": []})
                results[word] = {"bidding_apps_count": 0, "top_bidders": []}
            if i % 10 == 0:
                log(f"    {i}/{len(to_fetch)} done")

        browser.close()

    return results
