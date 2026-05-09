#!/usr/bin/env python3
"""Discover the upup endpoint that returns 'keywords this app is bidding on'.

Tries several plausible app URLs that might host the ASA/paid keywords view
and captures every api.upup.com XHR.
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import UPUP_AUTH_STATE

OUTPUT = ROOT / "cache" / "upup_app_bidding.jsonl"

APP_ID = "ygguvu633kd1dt6"
COUNTRY = 25
URLS_TO_TRY = [
    f"https://www.upup.com/app/{APP_ID}/ios-asa?market=1&country={COUNTRY}",
    f"https://www.upup.com/app/{APP_ID}/ios-paid?market=1&country={COUNTRY}",
    f"https://www.upup.com/app/{APP_ID}/ios-bidding?market=1&country={COUNTRY}",
    f"https://www.upup.com/app/{APP_ID}/ios-aso?market=1&country={COUNTRY}&tab=asa",
    f"https://www.upup.com/app/{APP_ID}/ios-aso?market=1&country={COUNTRY}&type=4",
    f"https://www.upup.com/app/{APP_ID}?market=1&country={COUNTRY}&tab=bidding",
]


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

        seen_urls: set[str] = set()

        def on_response(resp):
            try:
                if "api.upup.com" not in resp.url:
                    return
                if "application/json" not in resp.headers.get("content-type", "").lower():
                    return
                base = resp.url.split("?")[0]
                if base in seen_urls:
                    return
                seen_urls.add(base)
                body = resp.text()
                entry = {
                    "url": resp.url[:200],
                    "body_preview": body[:400],
                    "body_length": len(body),
                }
                with OUTPUT.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                print(f"  [{resp.status}] {base}")
            except Exception:
                pass

        page.on("response", on_response)
        page.set_default_navigation_timeout(30_000)

        for url in URLS_TO_TRY:
            print(f"\n→ {url}")
            try:
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)
            except PWTimeoutError:
                pass

        browser.close()

    print(f"\nUnique upup endpoints touched: {len(seen_urls)}")


if __name__ == "__main__":
    main()
