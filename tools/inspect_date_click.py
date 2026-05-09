#!/usr/bin/env python3
"""Try clicking the Custom date picker to find the shortcut buttons (Last 7/30 days)."""
from __future__ import annotations
import os, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import UPUP_AUTH_STATE

URL = "https://www.upup.com/app/yemupuvj9dp26cr/asa?market=1&country=25&system=4&id=1447098963&n=Call%20Recorder%20iCall"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=UPUP_AUTH_STATE if os.path.exists(UPUP_AUTH_STATE) else None, locale="en-US")
        context.add_init_script("localStorage.setItem('country','25'); localStorage.setItem('market','1');")
        page = context.new_page()
        page.set_default_navigation_timeout(45_000)
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)

        # Click on the Custom input to open date picker
        custom_input = page.query_selector('input[placeholder="Custom"]')
        if custom_input:
            print("Found Custom input, clicking...")
            custom_input.click()
            page.wait_for_timeout(1500)

            # After click, look for shortcut buttons
            print("\nLooking for shortcut buttons in opened picker:")
            shortcuts = page.query_selector_all('.el-picker-panel__shortcut, button, .shortcut-item')
            for s in shortcuts[:30]:
                try:
                    text = (s.inner_text() or "").strip()
                    if text and len(text) < 30:
                        cls = s.evaluate('e=>e.className')
                        if 'picker' in cls or 'shortcut' in cls or text in ['Today', 'Yesterday', 'Last 7 Days', 'Last 30 Days', 'Last Month', 'Custom']:
                            print(f"  text={text!r} class={cls}")
                except Exception:
                    pass

        browser.close()


if __name__ == "__main__":
    main()
