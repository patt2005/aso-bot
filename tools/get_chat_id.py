#!/usr/bin/env python3
"""Print chat_ids the bot has seen recently.

Usage:
  1. Add the bot to your group, give it admin rights (so it can post files).
  2. Send a message in the group that mentions the bot, e.g.  @aso_sniper_bot ping
  3. Run this script — it lists each chat with id, type, and title.
  4. Pick the right chat_id and put it in .env as TELEGRAM_CHAT_ID.
"""
from __future__ import annotations
import sys
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import TELEGRAM_BOT_TOKEN


def main():
    if not TELEGRAM_BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN missing in .env")
        sys.exit(1)

    resp = requests.get(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    updates = data.get("result", [])

    if not updates:
        print("No updates yet. Make sure you:")
        print("  1. Added the bot to a chat/group")
        print("  2. Sent a message that mentions the bot (e.g. '@aso_sniper_bot ping')")
        return

    seen: dict[int, dict] = {}
    for upd in updates:
        msg = upd.get("message") or upd.get("edited_message") or upd.get("channel_post")
        if not msg:
            continue
        chat = msg.get("chat") or {}
        cid = chat.get("id")
        if cid is not None and cid not in seen:
            seen[cid] = {
                "type": chat.get("type"),
                "title": chat.get("title") or chat.get("username") or chat.get("first_name", ""),
            }

    print(f"Found {len(seen)} unique chat(s):\n")
    for cid, info in seen.items():
        print(f"  chat_id = {cid}")
        print(f"    type:  {info['type']}")
        print(f"    title: {info['title']}\n")


if __name__ == "__main__":
    main()
