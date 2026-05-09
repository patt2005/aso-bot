#!/usr/bin/env python3
"""Capture XHR for the ASA bidding-words page of a specific app."""
from __future__ import annotations
import json, os, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import UPUP_AUTH_STATE

OUTPUT = ROOT / "cache" / "upup_asa.jsonl"
URL = "https://www.upup.com/app/yemupuvj9dp26cr/asa?market=1&country=25&system=4&id=1447098963&n=Call%20Recorder%20iCall"


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

        def on_response(resp):
            try:
                if "api.upup.com" not in resp.url:
                    return
                if "application/json" not in resp.headers.get("content-type", "").lower():
                    return
                body = resp.text()
                entry = {"url": resp.url[:250], "body": body[:18000], "body_length": len(body)}
                with OUTPUT.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                base = resp.url.split("?")[0]
                print(f"  [{resp.status}] {base} ({len(body)} bytes)")
            except Exception as e:
                print(f"  err: {e}")

        page.on("response", on_response)
        page.set_default_navigation_timeout(60_000)
        print(f"Navigating to {URL}\n")
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        # Scroll to bottom to trigger Keyword Details lazy load
        for _ in range(5):
            page.mouse.wheel(0, 800)
            page.wait_for_timeout(800)
        page.wait_for_timeout(5000)
        browser.close()

    print(f"\nSaved -> {OUTPUT}")


if __name__ == "__main__":
    main()
