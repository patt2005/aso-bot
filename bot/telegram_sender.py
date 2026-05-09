"""Send the generated xlsx report to a Telegram chat.

Mirrors the pattern from the C# TelegramNotificationService:
  token + chat_id + simple send method.
"""
from __future__ import annotations
from pathlib import Path
import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


API_BASE = "https://api.telegram.org"


def send_message(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not configured")
    requests.post(
        f"{API_BASE}/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data={"chat_id": TELEGRAM_CHAT_ID, "text": text},
        timeout=30,
    ).raise_for_status()


def send_document(file_path: str | Path, caption: str = "") -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not configured")
    file_path = Path(file_path)
    with file_path.open("rb") as f:
        resp = requests.post(
            f"{API_BASE}/bot{TELEGRAM_BOT_TOKEN}/sendDocument",
            data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
            files={"document": (file_path.name, f)},
            timeout=120,
        )
    resp.raise_for_status()
