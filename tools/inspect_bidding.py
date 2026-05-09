#!/usr/bin/env python3
"""Navigate directly to upup's Paid Bidding view and capture XHR calls.

URL pattern (from user's browser bar):
    https://www.upup.com/search/ios-1-4-1-25-1-telefon?time=&device=1
                               ^ ^ ^ ^^  ^
                               | | | |   `category
                               | | | `country
                               | | `version?
                               | `type (4 = Paid Bidding view)
                               `market

Saves all upup api responses (with full body up to 16KB) so we can find the
endpoint that returns the "Most Popular Paid Bidding Apps" table.
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import UPUP_AUTH_STATE

OUTPUT = ROOT / "cache" / "upup_bidding.jsonl"
URL = "https://www.upup.com/search/ios-1-4-1-25-1-telefon?time=&device=1"


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT.exists():
        OUTPUT.unlink()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx_kwargs = {"locale": "en-US"}
        if os.path.exists(UPUP_AUTH_STATE):
            ctx_kwargs["storage_state"] = UPUP_AUTH_STATE
        context = browser.new_context(**ctx_kwargs)
        context.add_init_script(
            "localStorage.setItem('country','25'); localStorage.setItem('market','1');"
        )
        page = context.new_page()

        captures: list[dict] = []

        def on_response(resp):
            try:
                if "api.upup.com" not in resp.url:
                    return
                if "application/json" not in resp.headers.get("content-type", "").lower():
                    return
                body = resp.text()
                entry = {
                    "url": resp.url,
                    "status": resp.status,
                    "body": body[:16000],
                    "body_length": len(body),
                }
                captures.append(entry)
                with OUTPUT.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                print(f"  [{resp.status}] {resp.url[:140]}")
            except Exception as e:
                print(f"  (capture failed: {e})")

        page.on("response", on_response)
        page.set_default_navigation_timeout(60_000)

        print(f"Navigating to {URL}")
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_timeout(8000)
        browser.close()

    print(f"\n{len(captures)} api.upup.com responses captured -> {OUTPUT}")


if __name__ == "__main__":
    main()
