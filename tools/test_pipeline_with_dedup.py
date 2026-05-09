#!/usr/bin/env python3
"""End-to-end production-path test: same code as bot/listener.py but called directly.

Filters out:
  - keywords already in seeds (already targeted in Apple Search Ads)
  - keywords already sent in past reports (SQLite history)

Sends xlsx to the configured Telegram chat.
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bot.listener import run_pipeline_and_send, DEFAULT_USER_ID  # noqa
from config import TELEGRAM_CHAT_ID


def main():
    adam_id = "6746982805"
    country_iso = "RO"
    chat_id = int(TELEGRAM_CHAT_ID) if TELEGRAM_CHAT_ID else 0

    print(f"adamId:     {adam_id}")
    print(f"country:    {country_iso}")
    print(f"telegram:   {chat_id}")
    print(f"user_id:    {DEFAULT_USER_ID}")
    print("\nStarting pipeline (3-5 minutes)...\n")

    t0 = time.time()
    run_pipeline_and_send(adam_id, country_iso, chat_id)
    print(f"\nDone in {time.time() - t0:.1f}s — check Telegram.")


if __name__ == "__main__":
    main()
