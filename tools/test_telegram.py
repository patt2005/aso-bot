#!/usr/bin/env python3
"""Quick smoke test for the Telegram bot integration.

Sends a hello message and the most recent xlsx report from output/.
Run AFTER setting TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bot.telegram_sender import send_message, send_document
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing in .env")
        sys.exit(1)

    print(f"Bot token: {TELEGRAM_BOT_TOKEN[:10]}...")
    print(f"Chat id:   {TELEGRAM_CHAT_ID}")

    print("\n[1/2] sending text message...")
    send_message("hello from ASO niche bot — test ping")
    print("  ok")

    output_dir = ROOT / "output"
    xlsx_files = sorted(output_dir.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not xlsx_files:
        print("\n[2/2] no xlsx in output/ — skipping document test")
        return

    latest = xlsx_files[0]
    print(f"\n[2/2] sending document: {latest.name}")
    send_document(latest, caption=f"test send · {latest.name}")
    print("  ok")

    print("\nCheck your Telegram chat now.")


if __name__ == "__main__":
    main()
