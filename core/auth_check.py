"""Verify the cached upup session still works.

Without a live login, the search-by-keyword and scrape-by-app endpoints
silently return 0 results. We check at the start of every daily run and
fire a Telegram alert if the session has expired so the operator knows to
re-login.
"""
from __future__ import annotations
import os
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

from config import UPUP_AUTH_STATE


def verify_upup_auth(timeout_ms: int = 15000) -> bool:
    """Return True if the cached auth state lands us on the logged-in UI."""
    if not os.path.exists(UPUP_AUTH_STATE):
        return False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(storage_state=UPUP_AUTH_STATE, locale="en-US")
            context.add_init_script(
                "localStorage.setItem('country','25'); localStorage.setItem('market','1');"
            )
            page = context.new_page()
            page.set_default_navigation_timeout(timeout_ms)
            try:
                page.goto("https://www.upup.com/", wait_until="domcontentloaded")
            except PWTimeoutError:
                return False

            # Wait for any redirect chain to settle (home -> login if expired).
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except PWTimeoutError:
                pass
            page.wait_for_timeout(2000)

            try:
                login_present = page.query_selector('input[type="password"]')
            except Exception:
                # Another navigation happened; treat as logged out to be safe.
                return False
            return login_present is None
        finally:
            browser.close()
