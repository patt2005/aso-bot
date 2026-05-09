"""Scrape an app's ASA (paid) bidding words from upup over a 30-day window.

Uses Playwright route interception to extend `start_time` on the asm/words
request before it leaves the browser — most apps have 0 bidding words today
but accumulate them over a week or two.
"""
from __future__ import annotations
import os
import time
from urllib.parse import urlparse, parse_qs, urlencode, quote
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

from config import UPUP_AUTH_STATE


ASM_WORDS_FRAGMENT = "/pc/v1/word/asm/words"
DAYS_BACK = 30


def asa_page_url(app_id: str, country: int, market: int = 1, ios_app_id: int | None = None, name: str = "") -> str:
    params = f"market={market}&country={country}&system=4"
    if ios_app_id:
        params += f"&id={ios_app_id}"
    if name:
        params += f"&n={quote(name)}"
    return f"https://www.upup.com/app/{app_id}/asa?{params}"


def get_bidding_words(
    app_id: str,
    country: int,
    market: int = 1,
    ios_app_id: int | None = None,
    name: str = "",
    days_back: int = DAYS_BACK,
    headless: bool = True,
) -> list[dict]:
    """Return the list of paid keywords this app has bid on in the last N days.

    Each item is the raw dict from upup's asm/words list — it includes name,
    popularity, search_index, asa_count, bidding_apps_count, bidding_ratio etc.
    """
    target_url = asa_page_url(app_id, country, market, ios_app_id, name)
    captured: list[dict] = []
    new_start_time = int(time.time()) - days_back * 86400

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

        def handle_route(route):
            req_url = route.request.url
            if ASM_WORDS_FRAGMENT in req_url:
                parsed = urlparse(req_url)
                params = parse_qs(parsed.query)
                params["start_time"] = [str(new_start_time)]
                params["page_size"] = ["200"]
                new_query = urlencode(params, doseq=True)
                new_url = parsed._replace(query=new_query).geturl()
                route.continue_(url=new_url)
                return
            route.continue_()

        page.route("https://api.upup.com/**", handle_route)

        def on_response(resp):
            try:
                if ASM_WORDS_FRAGMENT not in resp.url:
                    return
                if "application/json" not in resp.headers.get("content-type", "").lower():
                    return
                payload = resp.json()
                data = payload.get("data") or {}
                items = data.get("list") or []
                if items:
                    captured.extend(items)
            except Exception:
                pass

        page.on("response", on_response)
        page.set_default_navigation_timeout(45_000)

        try:
            page.goto(target_url, wait_until="domcontentloaded")
            page.wait_for_timeout(6000)
        except PWTimeoutError:
            pass

        browser.close()

    return captured
