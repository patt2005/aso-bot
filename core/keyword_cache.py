from __future__ import annotations
import json
import os
import sqlite3
import time
from dataclasses import asdict

from core.models import Keyword
from config import CACHE_DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS keyword_cache (
    app_id TEXT NOT NULL,
    country INTEGER NOT NULL,
    market INTEGER NOT NULL,
    scraped_at REAL NOT NULL,
    keywords_json TEXT NOT NULL,
    PRIMARY KEY (app_id, country, market)
)
"""


def _connect() -> sqlite3.Connection:
    db_dir = os.path.dirname(CACHE_DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(CACHE_DB_PATH)
    conn.execute(_SCHEMA)
    conn.commit()
    return conn


def get_cached(
    app_id: str,
    country: int,
    market: int,
    ttl_hours: float,
) -> list[Keyword] | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT scraped_at, keywords_json FROM keyword_cache "
            "WHERE app_id = ? AND country = ? AND market = ?",
            (app_id, country, market),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    scraped_at, keywords_json = row
    if (time.time() - scraped_at) > (ttl_hours * 3600):
        return None

    payload = json.loads(keywords_json)
    return [Keyword(**item) for item in payload]


def set_cached(
    app_id: str,
    country: int,
    market: int,
    keywords: list[Keyword],
) -> None:
    payload = json.dumps([asdict(k) for k in keywords])
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO keyword_cache (app_id, country, market, scraped_at, keywords_json) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(app_id, country, market) DO UPDATE SET "
            "scraped_at = excluded.scraped_at, keywords_json = excluded.keywords_json",
            (app_id, country, market, time.time(), payload),
        )
        conn.commit()
    finally:
        conn.close()


def clear_cache() -> None:
    conn = _connect()
    try:
        conn.execute("DELETE FROM keyword_cache")
        conn.commit()
    finally:
        conn.close()
