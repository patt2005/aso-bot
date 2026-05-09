#!/usr/bin/env python3
"""Daily entry-point: scan every (app, country) pair and send a Telegram report per geo.

Auto-detects countries from the user's `/api/keywords` endpoint — if the user
turns on a new geo in Apple Search Ads, the next run picks it up automatically
and sends a 🆕 NEW GEO alert to Telegram.

Tracks first-seen geos in SQLite so a country is only flagged "new" once.
"""
from __future__ import annotations
import datetime
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import base64
import os

from config import CACHE_DB_PATH, UPUP_AUTH_STATE
from core.pipeline import run_pipeline, default_output_path, DEFAULT_USER_ID
from core.seed_loader import load_seeds_by_country
from core.app_lookup import get_app_name
from core.auth_check import verify_upup_auth
from bot.telegram_sender import send_document, send_message


def hydrate_auth_state_from_env():
    """If UPUP_AUTH_STATE_BASE64 env var is set, decode it to the auth file.

    Avoids needing Railway CLI uploads. Set via Railway dashboard once after
    a fresh local login: `base64 -i cache/auth_state.json | pbcopy`.
    """
    encoded = os.getenv("UPUP_AUTH_STATE_BASE64")
    if not encoded:
        return
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except Exception as exc:
        print(f"  failed to decode UPUP_AUTH_STATE_BASE64: {exc}")
        return
    target = Path(UPUP_AUTH_STATE)
    if target.exists() and target.read_text(encoding="utf-8") == decoded:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(decoded, encoding="utf-8")
    print(f"  wrote auth state from env var -> {target}")


APPS = [
    {"adam_id": "6746982805", "user_id": DEFAULT_USER_ID},
]

GEO_TABLE = "geo_first_seen"


def _conn():
    Path(CACHE_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CACHE_DB_PATH)
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {GEO_TABLE} (
            adam_id TEXT NOT NULL,
            country_iso TEXT NOT NULL,
            first_seen REAL NOT NULL,
            PRIMARY KEY (adam_id, country_iso)
        )
        """
    )
    return conn


def is_new_geo(adam_id: str, country_iso: str) -> bool:
    with _conn() as conn:
        row = conn.execute(
            f"SELECT 1 FROM {GEO_TABLE} WHERE adam_id=? AND country_iso=?",
            (adam_id, country_iso),
        ).fetchone()
    return row is None


def mark_geo_seen(adam_id: str, country_iso: str) -> None:
    with _conn() as conn:
        conn.execute(
            f"INSERT OR IGNORE INTO {GEO_TABLE} (adam_id, country_iso, first_seen) VALUES (?, ?, ?)",
            (adam_id, country_iso, time.time()),
        )
        conn.commit()


def process_geo(adam_id: str, user_id: str, country_iso: str) -> None:
    app_name = get_app_name(adam_id, country=country_iso)
    new_geo = is_new_geo(adam_id, country_iso)

    if new_geo:
        send_message(
            f"🆕 NEW GEO DETECTED\n\n"
            f"📱 App: {app_name}\n"
            f"🌍 Country: {country_iso}\n\n"
            f"Running first niche analysis for this geo..."
        )

    output_path = default_output_path(adam_id, country_iso)
    stats = run_pipeline(adam_id, country_iso, output_path, user_id=user_id, record=True)

    if stats["new_keywords"] == 0 and not new_geo:
        print(f"  no new keywords for {adam_id} {country_iso} — skipping send")
        return

    caption = (
        f"🎯 ASO Daily Report"
        f"{' — NEW GEO' if new_geo else ''}\n"
        f"\n"
        f"📱 App: {app_name}\n"
        f"🌍 Country: {country_iso}\n"
        f"📅 {datetime.date.today().isoformat()}\n"
        f"\n"
        f"🆕 New keywords discovered: {stats['new_keywords']}"
    )
    send_document(output_path, caption=caption)
    mark_geo_seen(adam_id, country_iso)


UPUP_LOGIN_EMAIL = "ozunmihai5@gmail.com"


def main():
    print(f"=== {datetime.datetime.now().isoformat()} — daily multi-geo scan ===")

    hydrate_auth_state_from_env()

    print("Checking upup auth...")
    if not verify_upup_auth():
        print("  ❌ upup session expired — sending Telegram alert and aborting.")
        try:
            send_message(
                "🚨 upup authentication EXPIRED\n"
                "\n"
                "Daily ASO scan cannot run — login on upup.com has died.\n"
                "\n"
                f"Re-login needed with: {UPUP_LOGIN_EMAIL}\n"
                "\n"
                "Steps:\n"
                "1. cd aso-niche-finder (locally)\n"
                "2. rm cache/auth_state.json\n"
                "3. python3 tools/inspect_upup.py\n"
                "4. login in the browser, close it\n"
                "5. upload the new cache/auth_state.json to the Railway volume\n"
                "\n"
                "Once re-uploaded, the next cron run will resume normally."
            )
        except Exception as exc:
            print(f"  failed to send Telegram alert: {exc}")
        sys.exit(1)
    print("  ✓ upup auth is valid")

    for app in APPS:
        adam_id = app["adam_id"]
        user_id = app["user_id"]
        try:
            grouped = load_seeds_by_country(adam_id, user_id)
        except Exception as exc:
            print(f"  failed to load seeds for {adam_id}: {exc}")
            try:
                send_message(f"❌ Daily scan failed to load seeds for {adam_id}: {exc}")
            except Exception:
                pass
            continue

        countries = sorted(grouped.keys())
        print(f"  {adam_id}: {len(countries)} countries -> {countries}")

        for country_iso in countries:
            try:
                process_geo(adam_id, user_id, country_iso)
            except Exception as exc:
                print(f"  failed for {adam_id} {country_iso}: {exc}")
                try:
                    send_message(f"❌ Daily scan failed for {adam_id} {country_iso}: {exc}")
                except Exception:
                    pass

    print(f"=== {datetime.datetime.now().isoformat()} — done ===")


if __name__ == "__main__":
    main()
