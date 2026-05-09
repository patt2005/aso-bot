from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from typing import Literal

from config import CACHE_DB_PATH, OPENAI_API_KEY

INTENT_CLASSES = Literal[
    "core_niche",
    "competitor_brand",
    "long_tail_intent",
    "feature",
    "use_case",
    "generic_term",
    "irrelevant",
    "misspell",
]

_VALID_INTENTS = {
    "core_niche",
    "competitor_brand",
    "long_tail_intent",
    "feature",
    "use_case",
    "generic_term",
    "irrelevant",
    "misspell",
}

_BATCH_SIZE = 25
_TTL_SECONDS = 30 * 24 * 3600

_SCHEMA = """
CREATE TABLE IF NOT EXISTS keyword_classification_cache (
    keyword TEXT NOT NULL,
    app_context_hash TEXT NOT NULL,
    intent TEXT NOT NULL,
    confidence REAL NOT NULL,
    rationale TEXT NOT NULL,
    classified_at REAL NOT NULL,
    PRIMARY KEY (keyword, app_context_hash)
)
"""


@dataclass
class ClassifiedKeyword:
    name: str
    intent: str
    confidence: float
    rationale: str


def _connect() -> sqlite3.Connection:
    db_dir = os.path.dirname(CACHE_DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(CACHE_DB_PATH)
    conn.execute(_SCHEMA)
    conn.commit()
    return conn


def _context_hash(app_context: str) -> str:
    return hashlib.md5(app_context.encode()).hexdigest()[:12]


def _cache_get(keyword: str, ctx_hash: str) -> ClassifiedKeyword | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT intent, confidence, rationale, classified_at "
            "FROM keyword_classification_cache "
            "WHERE keyword = ? AND app_context_hash = ?",
            (keyword, ctx_hash),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    intent, confidence, rationale, classified_at = row
    if (time.time() - classified_at) > _TTL_SECONDS:
        return None

    return ClassifiedKeyword(
        name=keyword,
        intent=intent,
        confidence=float(confidence),
        rationale=rationale,
    )


def _cache_put(item: ClassifiedKeyword, ctx_hash: str) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO keyword_classification_cache "
            "(keyword, app_context_hash, intent, confidence, rationale, classified_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(keyword, app_context_hash) DO UPDATE SET "
            "intent = excluded.intent, "
            "confidence = excluded.confidence, "
            "rationale = excluded.rationale, "
            "classified_at = excluded.classified_at",
            (
                item.name,
                ctx_hash,
                item.intent,
                float(item.confidence),
                item.rationale,
                time.time(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _fallback(keywords: list[str]) -> list[ClassifiedKeyword]:
    return [
        ClassifiedKeyword(
            name=kw,
            intent="generic_term",
            confidence=0.0,
            rationale="GPT unavailable - heuristic fallback",
        )
        for kw in keywords
    ]


def _build_prompt(keywords: list[str], app_context: str) -> tuple[str, str]:
    system = (
        "You are an App Store Optimization (ASO) keyword analyst. "
        "Classify each keyword by its semantic intent relative to the target app. "
        "Allowed intent labels:\n"
        "- core_niche: main category keyword for the target app\n"
        "- competitor_brand: a competitor app or brand name\n"
        "- long_tail_intent: a specific multi-word use case query\n"
        "- feature: a specific product feature\n"
        "- use_case: a who/when scenario (audience, occasion)\n"
        "- generic_term: too broad or generic to target\n"
        "- irrelevant: noise, wrong language, off-topic\n"
        "- misspell: a typo of another keyword\n"
        "Respond ONLY with JSON of the form: "
        '{"results": [{"name": "...", "intent": "...", "confidence": 0.0-1.0, "rationale": "short reason"}]}. '
        "Preserve the exact input order and the exact keyword text in `name`."
    )
    user_payload = {
        "app_context": app_context,
        "keywords": keywords,
    }
    user = (
        "Classify these keywords for the given app. "
        "Return one result per keyword in the same order.\n"
        + json.dumps(user_payload, ensure_ascii=False)
    )
    return system, user


def _call_gpt(
    keywords: list[str],
    app_context: str,
    model: str,
) -> list[ClassifiedKeyword] | None:
    if not OPENAI_API_KEY:
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=OPENAI_API_KEY)
        system, user = _build_prompt(keywords, app_context)
        resp = client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = resp.choices[0].message.content
        if not content:
            return None
        data = json.loads(content)
        results = data.get("results")
        if not isinstance(results, list) or len(results) != len(keywords):
            return None

        out: list[ClassifiedKeyword] = []
        for kw, item in zip(keywords, results):
            if not isinstance(item, dict):
                return None
            intent = item.get("intent")
            if intent not in _VALID_INTENTS:
                return None
            try:
                confidence = float(item.get("confidence", 0.0))
            except (TypeError, ValueError):
                return None
            rationale = str(item.get("rationale", ""))
            name = item.get("name") or kw
            if name != kw:
                name = kw
            out.append(
                ClassifiedKeyword(
                    name=name,
                    intent=intent,
                    confidence=max(0.0, min(1.0, confidence)),
                    rationale=rationale,
                )
            )
        return out
    except Exception:
        return None


def classify_batch(
    keywords: list[str],
    app_context: str,
    model: str = "gpt-4o-mini",
) -> list[ClassifiedKeyword]:
    if not keywords:
        return []

    ctx_hash = _context_hash(app_context)

    cached: dict[str, ClassifiedKeyword] = {}
    uncached: list[str] = []
    seen: set[str] = set()
    for kw in keywords:
        if kw in seen:
            continue
        seen.add(kw)
        hit = _cache_get(kw, ctx_hash)
        if hit is not None:
            cached[kw] = hit
        else:
            uncached.append(kw)

    fresh: dict[str, ClassifiedKeyword] = {}
    for start in range(0, len(uncached), _BATCH_SIZE):
        chunk = uncached[start : start + _BATCH_SIZE]
        gpt_result = _call_gpt(chunk, app_context, model)
        if gpt_result is None:
            gpt_result = _fallback(chunk)
            for item in gpt_result:
                fresh[item.name] = item
        else:
            for item in gpt_result:
                fresh[item.name] = item
                if item.rationale != "GPT unavailable - heuristic fallback":
                    _cache_put(item, ctx_hash)

    output: list[ClassifiedKeyword] = []
    for kw in keywords:
        if kw in cached:
            output.append(cached[kw])
        elif kw in fresh:
            output.append(fresh[kw])
        else:
            output.append(
                ClassifiedKeyword(
                    name=kw,
                    intent="generic_term",
                    confidence=0.0,
                    rationale="GPT unavailable - heuristic fallback",
                )
            )
    return output


def classify_single(
    keyword: str,
    app_context: str,
    model: str = "gpt-4o-mini",
) -> ClassifiedKeyword:
    return classify_batch([keyword], app_context, model)[0]
