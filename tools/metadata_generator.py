"""ASO Metadata Generator
========================
Generates App Store metadata (Title, Subtitle, Keywords field, Promo Text,
Subscription description) for a given app + locale by:

  1. Loading ASA paid keywords from upup (market-validated demand signal)
  2. Loading top-ranked organic keywords for the app from upup
  3. Merging + scoring both sources into a ranked token pool
  4. Sending the ranked pool to GPT-4o with a carefully crafted prompt that
     understands the 2026 ASO ranking hierarchy
  5. Validating the output (no token repeats across fields, char limits)
  6. Re-prompting GPT with explicit violation list if validation fails

Usage:
  python tools/metadata_generator.py \
    --app-id <upup_app_id> \
    --ios-id  <itunes_adam_id> \
    --locale  US \
    [--user-id <uuid>] \
    [--max-retries 3]

Parameters:
  --app-id      upup app identifier (the string in the upup URL)
  --ios-id      iTunes adamId (numeric) used to pull ASA seeds + app name
  --locale      ISO country code, e.g. US, RO, DE, GB
  --user-id     UUID used by the seed endpoint (optional — skips ASA seeds if omitted)
  --max-retries Max GPT correction loops before surfacing to human review (default 3)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.app_lookup import get_app_name
from core.asa_words_scraper import get_bidding_words
from core.country_map import to_upup_country
from core.keyword_scraper import get_keywords
from core.seed_loader import load_seeds_with_revenue

# ---------------------------------------------------------------------------
# Char limits (Apple App Store 2026)
# ---------------------------------------------------------------------------
LIMITS = {
    "title":        30,
    "subtitle":     30,
    "keywords":     100,
    "promo_text":   170,
    "subscription": 255,   # subscription description
    # In-App Purchase fields — 3 plans, each with name (35) + description (55)
    "iap_weekly_name":        35,
    "iap_weekly_description": 55,
    "iap_monthly_name":        35,
    "iap_monthly_description": 55,
    "iap_yearly_name":        35,
    "iap_yearly_description": 55,
}

REVENUE_BASE        = 0.0   # flat bonus for any revenue > 0 (keep 0, let scale do the work)
REVENUE_SCALE       = 10.0  # score points per $1 of revenue
POPULARITY_WEIGHT   = 0.3   # popularity is a weak tiebreaker, not the main signal
ASA_BOOST           = 1.15  # small boost for keywords seen in upup ASA bidding
SEED_BOOST          = 1.50  # strong boost for active ASA campaign keywords (real spend validated)


# ---------------------------------------------------------------------------
# Step 1 — Collect & merge keyword sources
# ---------------------------------------------------------------------------

def _compute_score(popularity: float, revenue: float) -> float:
    """
    Score = revenue_component + popularity_component

    Revenue is the primary signal:
      $0   revenue → 0 revenue pts
      $10  revenue → 100 pts
      $24  revenue → 240 pts

    Popularity is a secondary tiebreaker:
      pop=71 → 21.3 pts   (whatsapp business — big brand, not our niche)
      pop=50 → 15.0 pts

    So a $24 revenue keyword (~240 pts) will always rank above
    a popularity-71 keyword with no revenue (~21 pts).
    """
    revenue_pts    = revenue * REVENUE_SCALE
    popularity_pts = popularity * POPULARITY_WEIGHT
    return round(revenue_pts + popularity_pts, 3)


def collect_keywords(
    app_id: str,
    ios_id: str,
    country_code: str,
    user_id: str | None,
) -> list[dict]:
    """
    Returns a merged list of dicts:
      { name, popularity, score, revenue, sources: [str] }
    sorted by score descending.
    Revenue is carried through so GPT can see real dollars per keyword.
    """
    upup_country = to_upup_country(country_code)
    pool: dict[str, dict] = {}

    print(f"[1/3] Fetching organic upup keywords for app={app_id}, country={upup_country}…")
    try:
        organic = get_keywords(app_id, country=upup_country, use_cache=False)
        for kw in organic:
            key = kw.name.strip().lower()
            pop = float(kw.popularity or 0)
            pool[key] = {
                "name": key,
                "popularity": pop,
                "revenue": 0.0,
                "score": _compute_score(pop, 0.0),
                "sources": ["organic"],
            }
        print(f"    → {len(organic)} organic keywords loaded")
    except Exception as exc:
        print(f"    [warn] organic keyword fetch failed: {exc}")

    print(f"[2/3] Fetching ASA bidding words for app={app_id}…")
    try:
        bidding = get_bidding_words(app_id, country=upup_country)
        for item in bidding:
            key = (item.get("name") or "").strip().lower()
            if not key:
                continue
            pop = float(item.get("popularity") or item.get("pop") or 0)
            if key in pool:
                pool[key]["popularity"] = max(pool[key]["popularity"], pop)
                if "asa_bidding" not in pool[key]["sources"]:
                    pool[key]["sources"].append("asa_bidding")
            else:
                pool[key] = {
                    "name": key,
                    "popularity": pop,
                    "revenue": 0.0,
                    "score": _compute_score(pop, 0.0) * ASA_BOOST,
                    "sources": ["asa_bidding"],
                }
        print(f"    → {len(bidding)} ASA bidding words loaded")
    except Exception as exc:
        print(f"    [warn] ASA bidding fetch failed: {exc}")

    # --- Source C: ASA seed keywords with revenue ---
    if user_id:
        print(f"[3/3] Fetching ASA seed keywords with revenue for adam_id={ios_id}…")
        try:
            seeds = load_seeds_with_revenue(ios_id, user_id, country_code=country_code)
            revenue_kws = 0
            for seed in seeds:
                key     = seed["text"].strip().lower()
                revenue = seed["revenue"]
                if key in pool:
                    # Recalculate score now that we have revenue / seed signal
                    pool[key]["revenue"] = max(pool[key]["revenue"], revenue)
                    base = _compute_score(pool[key]["popularity"], pool[key]["revenue"])
                    # Apply seed boost when keyword has no revenue (pure campaign spend signal)
                    pool[key]["score"] = base if revenue > 0 else base * SEED_BOOST
                    tag = "asa_revenue" if revenue > 0 else "asa_seed"
                    if tag not in pool[key]["sources"]:
                        pool[key]["sources"].append(tag)
                else:
                    multiplier = 1.0 if revenue > 0 else SEED_BOOST
                    pool[key] = {
                        "name": key,
                        "popularity": 0.0,
                        "revenue": revenue,
                        "score": _compute_score(0.0, revenue) * multiplier,
                        "sources": ["asa_revenue" if revenue > 0 else "asa_seed"],
                    }
                if revenue > 0:
                    revenue_kws += 1
            print(f"    → {len(seeds)} ASA seeds loaded ({revenue_kws} with revenue > $0)")
        except Exception as exc:
            print(f"    [warn] ASA seed fetch failed: {exc}")
    else:
        print("[3/3] Skipping ASA seeds (no --user-id provided)")

    merged = sorted(pool.values(), key=lambda x: x["score"], reverse=True)
    print(f"\n    Total merged keyword pool: {len(merged)} unique keywords\n")
    return merged


# ---------------------------------------------------------------------------
# Step 2 — Tokenize (used only for validation, not for GPT input)
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    """Split text into lowercase word tokens for repeat/derivative validation only."""
    latin_only = re.sub(r"[a-zA-Z0-9\s\-_']", "", text)
    if latin_only.strip():
        # Non-Latin — treat the whole phrase as one unit
        token = text.strip().lower()
        return {token} if token else set()
    return {t for t in re.findall(r"[a-z]+", text.lower()) if len(t) > 1}


# ---------------------------------------------------------------------------
# Step 3 — GPT metadata generation
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert App Store Optimization (ASO) specialist with 10+ years
of experience growing iOS apps from zero to top charts. Your role is to craft metadata
that maximizes keyword ranking coverage and drives organic installs. You understand
exactly how Apple's 2026 ranking algorithm weighs each metadata field, and you make
every character count. You think like a growth engineer — data first, brand second.

RANKING HIERARCHY you must respect when placing keywords:
  1. App Title (30 chars) — HIGHEST weight. Apple's algorithm weights keywords in the
     Title above all other fields. A keyword in the Title outranks the same keyword
     placed anywhere else. Lead with the highest-value keyword phrase — do NOT
     prioritize the brand name, this app has no brand recognition yet and every
     character must serve keyword ranking. Pack the most important keyword phrase
     naturally, the title must still read as human text.
  2. Subtitle (30 chars) — HIGH weight. Second most important surface. Use it for
     keyword variations that COMPLEMENT the Title, never echo it.
  3. Keyword Field (100 chars) — HIGH weight, hidden from users. Comma-separated,
     no spaces after commas, no articles (a, the, and, or). Fill every character.
     Apple's algorithm COMBINES tokens across all fields, so individual tokens here
     pair with tokens in Title/Subtitle automatically.
  4. Promotional Text (170 chars) — MEDIUM weight, editable without app review.
     Write a compelling marketing sentence that weaves in secondary keywords naturally.
  5. Subscription Description (255 chars) — MEDIUM weight. Describe the subscription
     value proposition with natural language and relevant keywords.
  6. In-App Purchase Names (35 chars each) — LOW weight but indexed by Apple.
     Generate 3 IAP plans: Weekly, Monthly, and Yearly. Each name must read as a
     real product name and use keywords NOT already used in title/subtitle/keywords.
     Each plan should emphasize different secondary keywords to maximize coverage.
     Examples: "Weekly – Unlimited Call Recorder", "Monthly Premium Plan – Transcribe",
     "Yearly Pro – Voice Memo & Backup".
  7. In-App Purchase Descriptions (55 chars each) — One per plan. Natural sentence
     describing what unlocks. Weave in remaining secondary keywords.

ABSOLUTE RULES — read each one carefully before writing a single character:

  RULE 1 — NO EXACT TOKEN REPEATS across title, subtitle, and keywords.
  Before finalising, extract every individual word (lowercase) from title,
  subtitle, and keywords. If ANY word appears in more than one field, remove it
  from the lower-priority field. Priority order: title > subtitle > keywords.
  Example violation: title has "Recorder", subtitle has "Recordings", keywords
  has "record" — all three share the root and at least two share the exact token
  after lowercasing. Fix: keep "Recorder" in title, remove from subtitle and keywords.

  RULE 2 — NO DERIVATIVE / ROOT REPEATS across title, subtitle, and keywords.
  Apple's algorithm treats stemmed variants as the same keyword and gives NO extra
  credit for repeating them. Derivatives waste precious character budget.
  A "derivative" means any word that shares the same root stem:
    • record / recorder / recording / recordings / recorded / rec → same root
    • call / calls / calling / caller → same root
    • learn / learning / learner / learned → same root
  Choose ONE form (the most valuable for ranking) and place it in the highest-
  priority field (title first, subtitle second, keywords last). Do NOT use any
  other derivative of that root anywhere across the three fields.

  RULE 3 — FILL THE KEYWORD FIELD to as close to 100 chars as possible without
  exceeding it. Count characters before writing. Format: word,word,word — NO spaces
  after commas, NO articles (a, the, and, or, in, on, for), NO punctuation.

  RULE 4 — TITLE and SUBTITLE must read as natural human text. A user sees these
  in search results. They must be compelling and readable, not a raw keyword list.

  RULE 5 — COUNT CHARACTERS for every field before finalising. If a field exceeds
  its limit, remove words from the END until it fits. Never exceed limits.

SELF-CHECK before producing output:
  1. List all words in title (lowercase) → no word appears in subtitle or keywords
  2. List all words in subtitle (lowercase) → no word appears in title or keywords
  3. Check for derivative pairs across all three fields → none found
  4. Count chars: title ≤ 30, subtitle ≤ 30, keywords ≤ 100,
     iap_weekly_name ≤ 35, iap_weekly_description ≤ 55,
     iap_monthly_name ≤ 35, iap_monthly_description ≤ 55,
     iap_yearly_name ≤ 35, iap_yearly_description ≤ 55
  5. Keywords has no spaces after commas

OUTPUT FORMAT: Respond with a single valid JSON object, no markdown fences:
{
  "title": "...",
  "subtitle": "...",
  "keywords": "...",
  "promo_text": "...",
  "subscription_description": "...",
  "iap_weekly_name": "...",
  "iap_weekly_description": "...",
  "iap_monthly_name": "...",
  "iap_monthly_description": "...",
  "iap_yearly_name": "...",
  "iap_yearly_description": "...",
  "tokens_used": {
    "title": [...],
    "subtitle": [...],
    "keywords": [...]
  },
  "reasoning": "..."
}
"""


def _build_user_prompt(
    app_name: str,
    app_description: str,
    locale: str,
    keywords: list[dict],
    violations: list[str] | None = None,
) -> str:
    # Split by revenue presence — revenue keywords go first
    revenue_kws = [k for k in keywords if k.get("revenue", 0) > 0]
    regular_kws = [k for k in keywords if k.get("revenue", 0) <= 0]
    ordered = revenue_kws + regular_kws

    def _fmt(i: int, k: dict) -> str:
        rev = k.get("revenue", 0.0)
        rev_str = f"  revenue=${rev:.2f} ★PRIORITIZE★" if rev > 0 else ""
        sources = ",".join(k.get("sources", []))
        return (
            f"  {i+1:>3}. {k['name']:30s}  score={k['score']:.1f}"
            f"  pop={k.get('popularity', 0):.0f}  sources={sources}{rev_str}"
        )

    kw_lines = "\n".join(_fmt(i, k) for i, k in enumerate(ordered[:60]))

    revenue_summary = ""
    if revenue_kws:
        top_rev = sorted(revenue_kws, key=lambda x: x["revenue"], reverse=True)[:5]
        lines = "\n".join(
            f"  • \"{k['name']}\" — ${k['revenue']:.2f} revenue  pop={k.get('popularity',0):.0f}"
            for k in top_rev
        )
        revenue_summary = f"""
REVENUE SIGNAL — these keywords already generated real subscription revenue from
your ASA campaigns. They are PROVEN to convert paying users. The Title MUST START
with the highest-revenue keyword phrase that fits in 30 chars. No brand name prefix.
{lines}
"""

    base = f"""APP NAME: {app_name}
APP DESCRIPTION: {app_description}
TARGET LOCALE: {locale}
{revenue_summary}
RANKED KEYWORD LIST (revenue keywords first, marked ★PRIORITIZE★):
{kw_lines}

HOW TO USE THIS LIST:
- Each row is a full keyword phrase, ranked by ASO value (revenue first, then popularity)
- Place the highest-ranked keywords that fit naturally into Title first, then Subtitle
- The keywords field (hidden, comma-separated) should use individual words or short
  phrases from this list that were NOT already used in title or subtitle
- Apple combines words across all fields automatically, so single words in the
  keywords field pair with words in title/subtitle for extra ranking combinations

FIELD LIMITS:
  title:                   {LIMITS['title']} chars
  subtitle:                {LIMITS['subtitle']} chars
  keywords:                {LIMITS['keywords']} chars
  promo_text:              {LIMITS['promo_text']} chars
  subscription_description:{LIMITS['subscription']} chars
  iap_weekly_name:         {LIMITS['iap_weekly_name']} chars
  iap_weekly_description:  {LIMITS['iap_weekly_description']} chars
  iap_monthly_name:        {LIMITS['iap_monthly_name']} chars
  iap_monthly_description: {LIMITS['iap_monthly_description']} chars
  iap_yearly_name:         {LIMITS['iap_yearly_name']} chars
  iap_yearly_description:  {LIMITS['iap_yearly_description']} chars

Generate the full App Store metadata set following the system rules exactly.
PRIORITY FOR TITLE: the highest-revenue keyword phrase comes FIRST. Do NOT lead
with the brand name — this app does not have brand recognition yet, so the title
must be fully optimized for keyword ranking. Every character in the title must
serve discoverability. Put the most important keyword phrase first, naturally worded.
Revenue = proven purchase intent = most important ranking signal.
For IAP names: use keyword phrases not already used in title/subtitle/keywords field.
Spread different keywords across the 3 IAP names for maximum indexed coverage."""

    if violations:
        violation_text = "\n".join(f"  - {v}" for v in violations)
        base += f"""

CORRECTION REQUIRED — your previous output had these violations:
{violation_text}

Fix ONLY the violations above. Keep everything else as close to your prior
output as possible. Return the corrected JSON."""

    return base


# ---------------------------------------------------------------------------
# Step 4 — Validation
# ---------------------------------------------------------------------------

try:
    from nltk.stem import SnowballStemmer as _SnowballStemmer
    _stemmer = _SnowballStemmer("english")
    def _stem(token: str) -> str:
        return _stemmer.stem(token)
except ImportError:
    # Fallback: naive suffix stripping covers the most common cases
    def _stem(token: str) -> str:  # type: ignore[misc]
        for suffix in ("ings", "ing", "ions", "ion", "ers", "er", "es", "ed", "s"):
            if token.endswith(suffix) and len(token) - len(suffix) >= 3:
                return token[: -len(suffix)]
        return token


def _stem_map(tokens: set[str]) -> dict[str, str]:
    """Return {token: stem} for a set of tokens."""
    return {t: _stem(t) for t in tokens}


def validate_metadata(result: dict) -> list[str]:
    """Returns a list of violation strings. Empty list = valid."""
    violations: list[str] = []

    title_tokens    = _tokenize(result.get("title", ""))
    subtitle_tokens = _tokenize(result.get("subtitle", ""))
    kw_tokens       = _tokenize(result.get("keywords", ""))

    # --- Exact token repeats across fields ---
    ts_overlap  = title_tokens & subtitle_tokens
    tkw_overlap = title_tokens & kw_tokens
    skw_overlap = subtitle_tokens & kw_tokens

    for tok in sorted(ts_overlap):
        violations.append(f"Token '{tok}' appears in both title AND subtitle — remove from subtitle")
    for tok in sorted(tkw_overlap):
        violations.append(f"Token '{tok}' appears in both title AND keywords — remove from keywords")
    for tok in sorted(skw_overlap):
        violations.append(f"Token '{tok}' appears in both subtitle AND keywords — remove from keywords")

    # --- Derivative / stem repeats across fields ---
    title_stems    = _stem_map(title_tokens)
    subtitle_stems = _stem_map(subtitle_tokens)
    kw_stems       = _stem_map(kw_tokens)

    # Check title stems vs subtitle
    for t_tok, t_stem in title_stems.items():
        for s_tok, s_stem in subtitle_stems.items():
            if t_stem == s_stem and t_tok != s_tok:
                violations.append(
                    f"Derivative pair: title '{t_tok}' and subtitle '{s_tok}' share the same root "
                    f"— remove '{s_tok}' from subtitle, it adds no extra ranking value"
                )
    # Check title stems vs keywords
    for t_tok, t_stem in title_stems.items():
        for k_tok, k_stem in kw_stems.items():
            if t_stem == k_stem and t_tok != k_tok:
                violations.append(
                    f"Derivative pair: title '{t_tok}' and keywords '{k_tok}' share the same root "
                    f"— remove '{k_tok}' from keywords, replace with a different keyword"
                )
    # Check subtitle stems vs keywords
    for s_tok, s_stem in subtitle_stems.items():
        for k_tok, k_stem in kw_stems.items():
            if s_stem == k_stem and s_tok != k_tok:
                violations.append(
                    f"Derivative pair: subtitle '{s_tok}' and keywords '{k_tok}' share the same root "
                    f"— remove '{k_tok}' from keywords, replace with a different keyword"
                )

    # --- Char limits ---
    field_key_map = {
        "title":                  "title",
        "subtitle":               "subtitle",
        "keywords":               "keywords",
        "promo_text":             "promo_text",
        "subscription":           "subscription_description",
        "iap_weekly_name":        "iap_weekly_name",
        "iap_weekly_description": "iap_weekly_description",
        "iap_monthly_name":       "iap_monthly_name",
        "iap_monthly_description":"iap_monthly_description",
        "iap_yearly_name":        "iap_yearly_name",
        "iap_yearly_description": "iap_yearly_description",
    }
    for field, limit in LIMITS.items():
        key = field_key_map.get(field, field)
        val = result.get(key, "")
        if len(val) > limit:
            violations.append(
                f"Field '{key}' is {len(val)} chars — exceeds {limit}-char limit by {len(val)-limit}"
            )

    # --- Keywords format ---
    kw_field = result.get("keywords", "")
    if ", " in kw_field:
        violations.append("keywords field contains spaces after commas — use 'word,word' not 'word, word'")

    return violations


# ---------------------------------------------------------------------------
# Step 5 — Build and save prompt to file
# ---------------------------------------------------------------------------

def save_prompt(
    app_name: str,
    app_description: str,
    locale: str,
    keywords: list[dict],
    out_path: str,
) -> None:
    user_prompt = _build_user_prompt(app_name, app_description, locale, keywords)

    full_prompt = f"SYSTEM\n{'='*60}\n{SYSTEM_PROMPT}\n\nUSER\n{'='*60}\n{user_prompt}"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(full_prompt)

    print(f"\nPrompt saved to: {out_path}")
    print(f"Characters: {len(full_prompt)}")
    print("\nPaste the full content of that file into Claude to generate the metadata.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Build ASO metadata prompt from upup + ASA keywords")
    parser.add_argument("--app-id",       required=True, help="upup app identifier string")
    parser.add_argument("--ios-id",       required=True, help="iTunes adamId (numeric)")
    parser.add_argument("--locale",       required=True, help="ISO country code, e.g. US, RO, DE")
    parser.add_argument("--user-id",      default=None,  help="UUID for ASA seed endpoint (optional)")
    parser.add_argument("--description",  default="",    help="Short app description (1-3 sentences).")
    parser.add_argument("--top-keywords", type=int, default=60, help="How many top keywords to include (default 60)")
    args = parser.parse_args()

    locale = args.locale.upper()

    print(f"\nLooking up app name for adam_id={args.ios_id}…")
    app_name = get_app_name(args.ios_id, country=locale.lower())
    print(f"  App name: {app_name}")

    app_description = args.description or f"{app_name} — iOS app"

    keywords = collect_keywords(
        app_id=args.app_id,
        ios_id=args.ios_id,
        country_code=locale,
        user_id=args.user_id,
    )

    if not keywords:
        print("ERROR: No keywords collected. Check upup auth state and app_id.")
        sys.exit(1)

    top_keywords = keywords[:args.top_keywords]
    print(f"Top {len(top_keywords)} keywords selected\n")

    os.makedirs("cache", exist_ok=True)
    out_path = f"cache/prompt_{args.app_id}_{locale}.txt"

    save_prompt(
        app_name=app_name,
        app_description=app_description,
        locale=locale,
        keywords=top_keywords,
        out_path=out_path,
    )


if __name__ == "__main__":
    main()
