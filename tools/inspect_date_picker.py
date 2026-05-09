#!/usr/bin/env python3
"""Open ASA page and explore the date picker structure so we can automate it."""
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

        date_inputs = page.query_selector_all('input[placeholder*="date" i], input[placeholder*="Date" i], input.el-input__inner, input[readonly]')
        print(f"Found {len(date_inputs)} candidate date inputs:")
        for i, inp in enumerate(date_inputs):
            attrs = inp.evaluate('el => ({type: el.type, placeholder: el.placeholder, value: el.value, classes: el.className, readonly: el.readOnly})')
            print(f"  [{i}] {attrs}")

        print("\nLooking for date-picker-related buttons / spans:")
        candidates = page.query_selector_all('div, span, button')
        date_keywords = ["Today", "Last 7", "Last 30", "Custom", "Date Range", "Coverage History"]
        for el in candidates[:200]:
            try:
                text = (el.inner_text() or "").strip()
                if any(k.lower() in text.lower() for k in date_keywords) and len(text) < 50:
                    print(f"  text={text!r}  tag={el.evaluate('e=>e.tagName')}  classes={el.evaluate('e=>e.className')}")
            except Exception:
                pass

        browser.close()


if __name__ == "__main__":
    main()
