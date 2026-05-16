#!/usr/bin/env python3
"""Headful inspection tool to discover upup endpoints.

Opens upup in a real browser, captures every XHR/fetch JSON response, and
saves them to cache/upup_capture.jsonl. Use it to:

  - find the search-by-keyword endpoint URL
  - find the app-detail / keyword-list endpoint shape
  - find any other endpoint we want to call directly

Usage:
  python tools/inspect_upup.py
  → browser opens, navigate manually (search a keyword, click an app, etc.)
  → close the browser when done
  → inspect cache/upup_capture.jsonl

Each line in the output file is JSON:
  {"url": "...", "status": 200, "body_preview": "first 800 chars"}
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import UPUP_AUTH_STATE  # noqa: E402

OUTPUT = ROOT / "cache" / "upup_capture.jsonl"
START_URL = "https://www.upup.com/"

EMAIL = "petru@codbun.com"
PASSWORD = "VSuPzNcZw7sTWG!"

def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT.exists():
        OUTPUT.unlink()

    captures: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx_kwargs = {"locale": "en-US"}
        if os.path.exists(UPUP_AUTH_STATE):
            ctx_kwargs["storage_state"] = UPUP_AUTH_STATE
            print(f"Using auth state: {UPUP_AUTH_STATE}")
        else:
            print(f"No auth state — log in manually with: {EMAIL}")
        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()

        def on_response(resp):
            try:
                if resp.request.resource_type not in ("xhr", "fetch"):
                    return
                ctype = resp.headers.get("content-type", "").lower()
                if "application/json" not in ctype:
                    return
                body = resp.text()
                preview_size = 12000 if "api.upup.com" in resp.url else 800
                entry = {
                    "url": resp.url,
                    "method": resp.request.method,
                    "status": resp.status,
                    "body_preview": body[:preview_size],
                    "body_length": len(body),
                }
                captures.append(entry)
                with OUTPUT.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                print(f"  [{resp.status}] {resp.url[:120]}")
            except Exception as e:
                print(f"  (capture failed: {e})")

        page.on("response", on_response)

        print(f"\nOpening {START_URL}")
        print("→ Search a keyword in upup, click into an app, browse around.")
        print(f"→ All JSON XHR responses will be logged to: {OUTPUT}")
        print("→ Close the browser window when done.\n")

        page.goto(START_URL)
        page.wait_for_event("close", timeout=0)

        if not os.path.exists(UPUP_AUTH_STATE):
            context.storage_state(path=UPUP_AUTH_STATE)

    print(f"\nCaptured {len(captures)} JSON responses → {OUTPUT}")


if __name__ == "__main__":
    main()
