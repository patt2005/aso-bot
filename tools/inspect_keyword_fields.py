#!/usr/bin/env python3
"""Capture the FULL item array from upup's keyword detail endpoint.

We currently use indices [0,1,2,7] from each item. There may be more fields
including ads/ASA bidder data. This script dumps every index so we can spot
which field holds the bid-presence info.
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import UPUP_AUTH_STATE, DEFAULT_MARKET


APP_ID = "yemupuvj9dp26cr"  # Call Recorder iCall — we have it cached and it has lots of keywords
COUNTRY = 25
URL = f"https://www.upup.com/app/{APP_ID}/ios-aso?market={DEFAULT_MARKET}&country={COUNTRY}"


def main():
    captured = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx_kwargs = {"locale": "en-US"}
        if os.path.exists(UPUP_AUTH_STATE):
            ctx_kwargs["storage_state"] = UPUP_AUTH_STATE
        context = browser.new_context(**ctx_kwargs)
        context.add_init_script(
            f"localStorage.setItem('country','{COUNTRY}'); localStorage.setItem('market','1');"
        )
        page = context.new_page()

        def on_response(resp):
            try:
                if "/word/analysi/detail" not in resp.url:
                    return
                if "application/json" not in resp.headers.get("content-type", "").lower():
                    return
                data = resp.json()["data"]["list"]
                if data:
                    captured.extend(data[:5])
            except Exception:
                pass

        page.on("response", on_response)
        page.set_default_navigation_timeout(60_000)
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_timeout(15000)
        browser.close()

    if not captured:
        print("No data captured.")
        return

    print(f"Captured {len(captured)} sample items.\n")
    for i, item in enumerate(captured):
        print(f"=== Item {i} ===")
        if isinstance(item, list):
            for idx, val in enumerate(item):
                marker = "  <-- USED" if idx in (0, 1, 2, 7) else ""
                print(f"  [{idx}] = {json.dumps(val, ensure_ascii=False)}{marker}")
        else:
            print(json.dumps(item, ensure_ascii=False, indent=2))
        print()


if __name__ == "__main__":
    main()
