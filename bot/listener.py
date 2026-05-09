"""Telegram bot listener for `/niche <adamId> [country_iso]` commands.

Run as a long-lived process:
    python -m bot.listener
"""
from __future__ import annotations
import asyncio
import sys
from datetime import datetime
from pathlib import Path

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config import TELEGRAM_BOT_TOKEN


DEFAULT_USER_ID = "1789c9b1-73e7-4653-a6b7-01470694e825"
DEFAULT_COUNTRY_ISO = "RO"


HELP_TEXT = (
    "ASO Niche Finder bot\n\n"
    "Commands:\n"
    "  /niche <adamId> [country_iso] — run niche analysis (e.g. /niche 1234567890 RO)\n"
    "  /start — show this help message\n"
)


def run_pipeline_and_send(adam_id: str, country_iso: str, chat_id: int) -> None:
    """Synchronous pipeline: load seeds → find competitors → validate → scrape → score → DEDUP → export → send.

    Dedup keeps only NEW keywords: not already in seeds (already targeted) and
    not previously sent (history table). After sending, BEST+MEDIUM are
    recorded so they're excluded next run.
    """
    from core.seed_loader import load_seeds
    from core.country_map import to_upup_country
    from core.competitor_finder import find_competitors
    from core.niche_validator import filter_by_jaccard
    from core.keyword_scraper import get_keywords
    from core.scorer import aggregate_keywords, classify
    from core.dedup import exclude_seeds, exclude_history, record_history
    from core.exporter import to_excel
    from core.app_lookup import get_app_name
    from bot.telegram_sender import send_document

    seeds = load_seeds(adam_id, DEFAULT_USER_ID, country_iso)
    upup_country = to_upup_country(country_iso)

    candidates = find_competitors(seeds, country=upup_country)

    validated = filter_by_jaccard(candidates)[:8]
    for c in validated:
        c.validated = True

    for comp in validated:
        comp.keywords = get_keywords(comp.app_id, country=upup_country)

    scored = aggregate_keywords(validated, allowed_languages=["EN", country_iso])
    total_before = len(scored)
    scored = exclude_seeds(scored, seeds)
    after_seeds = len(scored)
    scored = exclude_history(scored, adam_id, country_iso)
    after_history = len(scored)

    classified = classify(scored)
    record_history(classified["BEST"] + classified["MEDIUM"], adam_id, country_iso)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_name = f"niche_{adam_id}_{country_iso}_{timestamp}.xlsx"
    output_path = to_excel(classified, validated, Path("output") / out_name)

    app_name = get_app_name(adam_id, country=country_iso)
    excluded_seeds_count = total_before - after_seeds
    excluded_history_count = after_seeds - after_history

    caption = (
        f"🎯 ASO Niche Report\n"
        f"\n"
        f"📱 App: {app_name}\n"
        f"🌍 Country: {country_iso}\n"
        f"\n"
        f"🆕 New keywords discovered: {after_history}\n"
        f"   🏆 BEST — must target: {len(classified['BEST'])}\n"
        f"   ⭐ MEDIUM — worth testing: {len(classified['MEDIUM'])}\n"
        f"   ⚪ Low value: {len(classified['TRASH'])}\n"
        f"\n"
        f"ℹ️ Filtered out:\n"
        f"   • {excluded_seeds_count} already in your campaigns\n"
        f"   • {excluded_history_count} previously sent\n"
        f"\n"
        f"📎 Full details in attached Excel"
    )
    send_document(output_path, caption=caption)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT)


async def niche(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []

    if not args:
        await update.message.reply_text(
            "Usage: /niche <adamId> [country_iso]\nExample: /niche 1234567890 RO"
        )
        return

    adam_id = args[0]
    if not adam_id.isdigit():
        await update.message.reply_text(
            f"Invalid adamId {adam_id!r} — must be all digits.\n"
            "Usage: /niche <adamId> [country_iso]"
        )
        return

    country_iso = (args[1] if len(args) >= 2 else DEFAULT_COUNTRY_ISO).upper()
    chat_id = update.effective_chat.id

    await update.message.reply_text(
        f"⏳ Running niche analysis for adamId={adam_id} country={country_iso}... "
        f"this can take 3-5 minutes."
    )

    try:
        # asyncio.to_thread keeps the bot event loop responsive while the
        # blocking Playwright/HTTP pipeline runs.
        await asyncio.to_thread(run_pipeline_and_send, adam_id, country_iso, chat_id)
    except Exception as exc:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Pipeline failed: {exc}")
        return

    await context.bot.send_message(chat_id=chat_id, text="✅ Done. Report sent above.")


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN is not set in .env — cannot start listener.", file=sys.stderr)
        sys.exit(1)

    print(f"Telegram listener starting on token {TELEGRAM_BOT_TOKEN[:10]}...")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("niche", niche))
    app.run_polling()


if __name__ == "__main__":
    main()
