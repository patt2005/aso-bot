#!/usr/bin/env python3
"""Headless capture of upup /dashboard XHR responses.

Opens https://www.upup.com/dashboard with the cached auth state, waits for
the page to settle, and dumps every JSON XHR/fetch response to
cache/upup_dashboard_capture.jsonl so we can identify the top-charts endpoint.
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

OUTPUT = ROOT / "cache" / "upup_dashboard_capture.jsonl"
URL = "https://www.upup.com/dashboard"


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT.exists():
        OUTPUT.unlink()

    if not os.path.exists(UPUP_AUTH_STATE):
        print(f"ERROR: no auth state at {UPUP_AUTH_STATE}")
        sys.exit(1)

    captures: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=UPUP_AUTH_STATE, locale="en-US")
        page = context.new_page()

        def on_response(resp):
            try:
                if resp.request.resource_type not in ("xhr", "fetch"):
                    return
                ctype = resp.headers.get("content-type", "").lower()
                if "application/json" not in ctype:
                    return
                body = resp.text()
                entry = {
                    "url": resp.url,
                    "method": resp.request.method,
                    "status": resp.status,
                    "body_preview": body[:4000],
                    "body_length": len(body),
                }
                captures.append(entry)
                with OUTPUT.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                print(f"  [{resp.status}] {resp.url[:140]}")
            except Exception as e:
                print(f"  (capture failed: {e})")

        page.on("response", on_response)

        print(f"Opening {URL}")
        page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(3000)

        title = page.title()
        url_final = page.url
        print(f"\nFinal URL: {url_final}")
        print(f"Title: {title}")

        browser.close()

    print(f"\nCaptured {len(captures)} JSON responses → {OUTPUT}")


if __name__ == "__main__":
    main()
