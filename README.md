# aso-niche-finder

Discovers high-value ASO keywords for an iOS app by:
1. Pulling seed keywords from your endpoint
2. Finding competitor apps that rank for those seeds (via upup)
3. Validating which competitors are truly in the same niche (Jaccard + category + GPT)
4. Scraping each validated competitor's keywords
5. Scoring & classifying (BEST / MEDIUM / TRASH)
6. Exporting an `.xlsx` and sending it to a dedicated Telegram bot

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env  # then fill in tokens
```

First-time upup login: run with `HEADFUL=True` in `core/keyword_scraper.py`, log in once, the session is saved to `cache/auth_state.json`.

## Run

```bash
python main.py --app-id emupu81vr05egfr --country 24
python main.py --seeds "meditation,sleep,mindfulness" --country 24 --no-telegram
```

## Project structure

```
core/
  seed_loader.py        # fetch seeds from endpoint  ← endpoint URL pending
  competitor_finder.py  # seed kw → top apps         ← upup search URL pending
  niche_validator.py    # Jaccard + category + GPT
  keyword_scraper.py    # ported from aso-sheets-service
  scorer.py             # score + classify into tiers
  exporter.py           # xlsx writer
bot/
  telegram_sender.py    # sendMessage / sendDocument
main.py                 # CLI + pipeline orchestration
```

## Pending integration points

- `core/seed_loader.py` — endpoint URL/method/response shape (waiting on user)
- `core/competitor_finder.py` — upup search endpoint URL & response parser (TODO via headful inspection)
- `bot/` — fill `.env` with new bot token + chat id once @BotFather gives them
