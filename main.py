#!/usr/bin/env python3
"""ASO Niche Finder — entry point.

Pipeline:
  1. Load seed keywords (from endpoint or CLI)
  2. Find competitor apps that rank for those seeds
  3. Validate which competitors are actually in our niche
  4. Scrape keywords for each validated competitor
  5. Score + classify (BEST / MEDIUM / TRASH)
  6. Export to xlsx
  7. Send to Telegram

Usage:
  python main.py --app-id emupu81vr05egfr --country 24
  python main.py --seeds "meditation,sleep sounds,mindfulness" --country 24
"""
from __future__ import annotations
import argparse
from datetime import datetime
from pathlib import Path

from core.seed_loader import load_seeds
from core.competitor_finder import find_competitors
from core.niche_validator import validate
from core.keyword_scraper import get_keywords
from core.scorer import aggregate_keywords, classify
from core.exporter import to_excel
from bot.telegram_sender import send_document, send_message
from config import DEFAULT_COUNTRY, TOP_COMPETITORS


def run(
    app_id: str | None,
    country: int,
    seeds: list[str] | None = None,
    seed_app_description: str = "",
    notify: bool = True,
) -> Path:
    if seeds is None:
        print("Loading seed keywords from endpoint...")
        seeds = load_seeds(app_id=app_id, country=country)
    print(f"  → {len(seeds)} seed keywords")

    print("Finding competitor apps...")
    candidates, keyword_top_apps = find_competitors(seeds, country=country)
    print(f"  → {len(candidates)} candidate competitors")

    print("Validating niche fit...")
    validated = validate(
        candidates,
        seed_app_description=seed_app_description,
        use_gpt=bool(seed_app_description),
    )[:TOP_COMPETITORS]
    print(f"  → {len(validated)} validated competitors")

    print("Scraping keywords per competitor...")
    for i, comp in enumerate(validated, 1):
        print(f"  [{i}/{len(validated)}] {comp.app_id}")
        comp.keywords = get_keywords(comp.app_id, country=country)

    print("Scoring + classifying...")
    scored = aggregate_keywords(validated, keyword_top_apps=keyword_top_apps)
    classified = classify(scored)
    print(
        f"  → BEST: {len(classified['BEST'])}, "
        f"MEDIUM: {len(classified['MEDIUM'])}, "
        f"TRASH: {len(classified['TRASH'])}"
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_name = f"niche_{app_id or 'manual'}_{country}_{timestamp}.xlsx"
    output_path = to_excel(classified, validated, Path("output") / out_name)
    print(f"Exported: {output_path}")

    if notify:
        caption = (
            f"ASO niche report\n"
            f"App: {app_id or '(manual seeds)'}  Country: {country}\n"
            f"BEST: {len(classified['BEST'])}  MEDIUM: {len(classified['MEDIUM'])}"
        )
        send_document(output_path, caption=caption)

    return output_path


def main():
    parser = argparse.ArgumentParser(description="ASO niche keyword finder")
    parser.add_argument("--app-id", help="Seed app id (used to fetch seeds from endpoint)")
    parser.add_argument("--seeds", help="Comma-separated seed keywords (overrides endpoint)")
    parser.add_argument("--country", type=int, default=DEFAULT_COUNTRY)
    parser.add_argument("--description", default="", help="Seed app description for GPT validator")
    parser.add_argument("--no-telegram", action="store_true")
    args = parser.parse_args()

    seeds = None
    if args.seeds:
        seeds = [s.strip() for s in args.seeds.split(",") if s.strip()]

    try:
        run(
            app_id=args.app_id,
            country=args.country,
            seeds=seeds,
            seed_app_description=args.description,
            notify=not args.no_telegram,
        )
    except Exception as exc:
        if not args.no_telegram:
            try:
                send_message(f"ASO niche run FAILED: {exc}")
            except Exception:
                pass
        raise


if __name__ == "__main__":
    main()
