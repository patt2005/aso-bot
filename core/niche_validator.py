"""Validate that candidate competitors are actually in our niche.

Three layers, each catches a different kind of false positive:
  1. Jaccard threshold on seed_overlap  — kills competitors that just rank
     on 1-2 generic keywords.
  2. Category match                     — kills competitors from totally
     different verticals.
  3. GPT relevance check (borderline)   — catches semantic nuance the first
     two miss.
"""
from __future__ import annotations
from openai import OpenAI

from core.models import Competitor
from config import OPENAI_API_KEY, JACCARD_THRESHOLD


_client: OpenAI | None = None


def _openai() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def filter_by_jaccard(competitors: list[Competitor], threshold: float = JACCARD_THRESHOLD) -> list[Competitor]:
    return [c for c in competitors if c.seed_overlap >= threshold]


def filter_by_category(competitors: list[Competitor], allowed_categories: list[str]) -> list[Competitor]:
    if not allowed_categories:
        return competitors
    allowed = {c.lower() for c in allowed_categories}
    return [c for c in competitors if c.category.lower() in allowed or not c.category]


def gpt_is_same_niche(seed_app_description: str, competitor_name: str, competitor_description: str) -> bool:
    """Ask GPT whether the competitor belongs to the same niche as the seed app."""
    prompt = (
        "You decide whether two iOS apps belong to the SAME ASO niche.\n\n"
        f"Our app:\n{seed_app_description}\n\n"
        f"Competitor: {competitor_name}\n{competitor_description}\n\n"
        "Reply with one word: SAME, RELATED, or DIFFERENT."
    )
    try:
        resp = _openai().chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=5,
            temperature=0,
        )
        verdict = resp.choices[0].message.content.strip().upper()
        return verdict in ("SAME", "RELATED")
    except Exception:
        return True


def validate(
    competitors: list[Competitor],
    seed_app_description: str = "",
    allowed_categories: list[str] | None = None,
    use_gpt: bool = True,
) -> list[Competitor]:
    pool = filter_by_jaccard(competitors)
    if allowed_categories:
        pool = filter_by_category(pool, allowed_categories)

    if use_gpt and seed_app_description:
        validated = []
        for c in pool:
            description = c.name
            if gpt_is_same_niche(seed_app_description, c.name, description):
                c.validated = True
                validated.append(c)
        return validated

    for c in pool:
        c.validated = True
    return pool
