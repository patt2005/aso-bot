#!/usr/bin/env python3
"""Open the ASA page, click Export Data, and capture both:
  - all api.upup.com XHRs (incl. the one that returns the keyword list)
  - the downloaded Excel file (saved to cache/asa_export.xlsx)
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import UPUP_AUTH_STATE

OUTPUT_LOG = ROOT / "cache" / "upup_asa_export.jsonl"
OUTPUT_FILE = ROOT / "cache" / "asa_export.xlsx"
URL = "https://www.upup.com/app/yemupuvj9dp26cr/asa?market=1&country=25&system=4&id=1447098963&n=Call%20Recorder%20iCall"


def main():
    OUTPUT_LOG.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_LOG.exists():
        OUTPUT_LOG.unlink()
    if OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx_kwargs = {"locale": "en-US"}
        if os.path.exists(UPUP_AUTH_STATE):
            ctx_kwargs["storage_state"] = UPUP_AUTH_STATE
        context = browser.new_context(accept_downloads=True, **ctx_kwargs)
        context.add_init_script(
            "localStorage.setItem('country','25'); localStorage.setItem('market','1');"
        )
        page = context.new_page()

        def on_response(resp):
            try:
                if "api.upup.com" not in resp.url:
                    return
                ctype = resp.headers.get("content-type", "").lower()
                body = resp.text() if "json" in ctype else f"<binary {len(resp.body())} bytes>"
                entry = {
                    "url": resp.url[:300],
                    "content_type": ctype,
                    "body": body[:18000] if isinstance(body, str) else body,
                    "body_length": len(body) if isinstance(body, str) else 0,
                }
                with OUTPUT_LOG.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                print(f"  [{resp.status}] {resp.url.split('?')[0]}")
            except Exception as e:
                print(f"  err: {e}")

        def on_download(download):
            print(f"\n  ⬇ DOWNLOAD: {download.suggested_filename}")
            print(f"     URL: {download.url}")
            download.save_as(OUTPUT_FILE)
            print(f"     Saved -> {OUTPUT_FILE}")

        page.on("response", on_response)
        page.on("download", on_download)
        page.set_default_navigation_timeout(60_000)

        print(f"Navigating to {URL}")
        print("→ in browser: click the orange Export Data button at the bottom right")
        print("→ then close the browser when the file is saved\n")

        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_event("close", timeout=0)


if __name__ == "__main__":
    main()
