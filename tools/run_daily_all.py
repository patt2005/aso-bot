#!/usr/bin/env python3
"""Daily entry-point: scan every (app, country) pair and send a Telegram report per geo.

Auto-detects countries from the user's `/api/keywords` endpoint — if the user
turns on a new geo in Apple Search Ads, the next run picks it up automatically.

Stateless: each run pulls the user's current keywords fresh from the endpoint
and filters them out from the discovered pool. No volume / no DB persistence
required — when a keyword is added to the user's campaign it disappears from
future reports automatically.
"""
from __future__ import annotations
import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import base64
import os

from config import UPUP_AUTH_STATE
from core.pipeline import run_pipeline, default_output_path, DEFAULT_USER_ID
from core.seed_loader import load_seeds_by_country
from core.app_lookup import get_app_name
from core.auth_check import verify_upup_auth
from core.niche_exporter import export_niches_to_excel
from bot.telegram_sender import send_document, send_message

sys.path.insert(0, str(ROOT / "tools"))
from niche_finder import fetch_rank_data, find_niches  # noqa: E402

NICHE_MIN_INCR = 50   # only STRONG / EXPLOSIVE signals
NICHE_MAX_RANK = 150
NICHE_TOP_N    = 50


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


def process_geo(adam_id: str, user_id: str, country_iso: str) -> None:
    app_name = get_app_name(adam_id, country=country_iso)
    output_path = default_output_path(adam_id, country_iso)
    stats = run_pipeline(adam_id, country_iso, output_path, user_id=user_id)

    if stats["new_keywords"] == 0:
        print(f"  no new keywords for {adam_id} {country_iso} — skipping send")
        return

    caption = (
        f"🎯 ASO Daily Report\n"
        f"\n"
        f"📱 App: {app_name}\n"
        f"🌍 Country: {country_iso}\n"
        f"📅 {datetime.date.today().isoformat()}\n"
        f"\n"
        f"🆕 New keywords discovered: {stats['new_keywords']}"
    )
    send_document(output_path, caption=caption)


UPUP_LOGIN_EMAIL = "mihaiozun5@gmail.com"


def run_niche_finder() -> None:
    """Fetch Top Free chart, score rising apps, export xlsx, send via Telegram."""
    print("\n--- Niche Finder ---")
    try:
        data = fetch_rank_data(country_id=24)
    except Exception as exc:
        print(f"  niche finder: failed to fetch rank data: {exc}")
        return

    if not data:
        print("  niche finder: no data returned (session may be invalid)")
        return

    niches = find_niches(
        data,
        min_incr=NICHE_MIN_INCR,
        max_rank=NICHE_MAX_RANK,
        top_n=NICHE_TOP_N,
        include_ads=False,
    )

    if not niches:
        print(f"  niche finder: no apps with rank jump >= {NICHE_MIN_INCR} found today")
        try:
            send_message(
                f"📊 Niche Finder — {datetime.date.today().isoformat()}\n"
                f"No apps with rank jump ≥ {NICHE_MIN_INCR} in Top Free today."
            )
        except Exception:
            pass
        return

    print(f"  niche finder: {len(niches)} opportunities found")

    output_path = ROOT / "cache" / f"niches_{datetime.date.today().isoformat()}.xlsx"
    try:
        export_niches_to_excel(niches, output_path)
        print(f"  niche finder: saved to {output_path}")
    except Exception as exc:
        print(f"  niche finder: excel export failed: {exc}")
        return

    top3 = niches[:3]
    top3_lines = "\n".join(
        f"  {i+1}. {n['name']} (+{n['rank_incr']} spots → #{n['rank']})  [{n['tier']}]"
        for i, n in enumerate(top3)
    )
    caption = (
        f"📈 App Store Niche Finder\n"
        f"📅 {datetime.date.today().isoformat()}\n"
        f"\n"
        f"🔥 {len(niches)} rising apps (rank jump ≥ {NICHE_MIN_INCR})\n"
        f"\n"
        f"Top movers:\n{top3_lines}\n"
        f"\n"
        f"Full report in the attached Excel."
    )
    try:
        send_document(str(output_path), caption=caption)
        print("  niche finder: report sent via Telegram")
    except Exception as exc:
        print(f"  niche finder: failed to send Telegram: {exc}")


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

    run_niche_finder()

    # for app in APPS:
    #     adam_id = app["adam_id"]
    #     user_id = app["user_id"]
    #     try:
    #         grouped = load_seeds_by_country(adam_id, user_id)
    #     except Exception as exc:
    #         print(f"  failed to load seeds for {adam_id}: {exc}")
    #         try:
    #             send_message(f"❌ Daily scan failed to load seeds for {adam_id}: {exc}")
    #         except Exception:
    #             pass
    #         continue
    #
    #     from core.country_map import ISO_TO_UPUP
    #     active_countries = sorted(grouped.keys())
    #     runnable = [c for c in active_countries if c in ISO_TO_UPUP]
    #     skipped = [c for c in active_countries if c not in ISO_TO_UPUP]
    #
    #     print(f"  {adam_id}: active campaigns in {active_countries}")
    #     print(f"    runnable: {runnable}")
    #     if skipped:
    #         print(f"    skipped (no upup id mapped): {skipped}")
    #
    #     for country_iso in runnable:
    #         try:
    #             process_geo(adam_id, user_id, country_iso)
    #         except Exception as exc:
    #             print(f"  failed for {adam_id} {country_iso}: {exc}")
    #             try:
    #                 send_message(f"❌ Daily scan failed for {adam_id} {country_iso}: {exc}")
    #             except Exception:
    #                 pass
    #
    # print(f"=== {datetime.datetime.now().isoformat()} — done ===")


if __name__ == "__main__":
    main()
