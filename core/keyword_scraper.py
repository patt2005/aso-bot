"""Scrape ASO keywords for an app from upup.com using Playwright.

Ported and slightly hardened from aso-sheets-service. Listens to XHR responses
and extracts keywords from the analysi/detail endpoint.
"""
from __future__ import annotations
import os
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

from core.models import Keyword
from core.keyword_cache import get_cached, set_cached
from config import UPUP_AUTH_STATE, MIN_POPULARITY, DEFAULT_MARKET, KEYWORD_CACHE_TTL_HOURS

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/118.0.0.0 Safari/537.36"
)

HEADFUL = False


def build_target_url(app_id: str, market: int, country: int) -> str:
    return f"https://www.upup.com/app/{app_id}/ios-aso?market={market}&country={country}"


def get_keywords(
    app_id: str,
    country: int,
    market: int = DEFAULT_MARKET,
    use_cache: bool = True,
) -> list[Keyword]:
    if use_cache:
        cached = get_cached(app_id, country, market, KEYWORD_CACHE_TTL_HOURS)
        if cached is not None:
            print(f"  [cache hit] {app_id}")
            return cached

    keywords = _scrape_keywords(app_id, country, market)

    if use_cache:
        set_cached(app_id, country, market, keywords)

    return keywords


def _scrape_keywords(app_id: str, country: int, market: int) -> list[Keyword]:
    target_url = build_target_url(app_id, market, country)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not HEADFUL)

        if os.path.exists(UPUP_AUTH_STATE):
            context = browser.new_context(
                storage_state=UPUP_AUTH_STATE,
                user_agent=DEFAULT_UA,
                locale="en-US",
            )
        else:
            context = browser.new_context(user_agent=DEFAULT_UA, locale="en-US")

        page = context.new_page()
        keywords: list[Keyword] = []

        def on_response(resp):
            try:
                req = resp.request
                if req.resource_type not in ("xhr", "fetch"):
                    return
                ctype = resp.headers.get("content-type", "").lower()
                if "application/json" not in ctype:
                    return
                if not resp.url.startswith("https://api.upup.com/pc/v1/word/analysi/detail"):
                    return

                data = resp.json()["data"]["list"]
                for item in data:
                    kw = Keyword(
                        name=item[0],
                        ranking=item[1],
                        change=item[2],
                        popularity=item[7],
                        total_apps=item[3] if len(item) > 3 else None,
                        ad_count=item[4] if len(item) > 4 else None,
                    )
                    if kw.popularity is not None and kw.popularity >= MIN_POPULARITY:
                        keywords.append(kw)
            except Exception:
                pass

        page.on("response", on_response)
        page.set_default_navigation_timeout(0)

        try:
            page.goto(target_url, wait_until="domcontentloaded")
        except PWTimeoutError:
            try:
                page.goto(target_url, wait_until="networkidle", timeout=120_000)
            except PWTimeoutError:
                pass

        if not os.path.exists(UPUP_AUTH_STATE):
            page.wait_for_event("close", timeout=0)
        else:
            page.wait_for_timeout(15000)
            page.close()

        if not os.path.exists(UPUP_AUTH_STATE):
            context.storage_state(path=UPUP_AUTH_STATE)

        browser.close()
        return keywords
