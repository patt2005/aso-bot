"""Filter out keywords we already target or have previously suggested.

Two sources of "not new":
  1. Seeds — keywords already in the user's Apple Search Ads campaigns.
  2. History — keywords we've sent in past reports (SQLite-backed).

Both filters compare on the normalized form (lowercased + collapsed whitespace).
"""
from __future__ import annotations
import sqlite3
import time
from pathlib import Path

from core.models import ScoredKeyword
from core.keyword_filter import normalize
from config import CACHE_DB_PATH


HISTORY_TABLE = "keyword_history"


def _conn() -> sqlite3.Connection:
    Path(CACHE_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CACHE_DB_PATH)
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {HISTORY_TABLE} (
            adam_id TEXT NOT NULL,
            country_iso TEXT NOT NULL,
            keyword TEXT NOT NULL,
            sent_at REAL NOT NULL,
            PRIMARY KEY (adam_id, country_iso, keyword)
        )
        """
    )
    return conn


def exclude_seeds(scored: list[ScoredKeyword], seeds: list[str]) -> list[ScoredKeyword]:
    seen = {normalize(s) for s in seeds}
    return [s for s in scored if normalize(s.name) not in seen]


def exclude_history(scored: list[ScoredKeyword], adam_id: str, country_iso: str) -> list[ScoredKeyword]:
    with _conn() as conn:
        rows = conn.execute(
            f"SELECT keyword FROM {HISTORY_TABLE} WHERE adam_id=? AND country_iso=?",
            (adam_id, country_iso.upper()),
        ).fetchall()
    seen = {row[0] for row in rows}
    return [s for s in scored if normalize(s.name) not in seen]


def record_history(scored: list[ScoredKeyword], adam_id: str, country_iso: str) -> int:
    if not scored:
        return 0
    now = time.time()
    rows = [(adam_id, country_iso.upper(), normalize(s.name), now) for s in scored]
    with _conn() as conn:
        conn.executemany(
            f"INSERT OR IGNORE INTO {HISTORY_TABLE} (adam_id, country_iso, keyword, sent_at) VALUES (?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    return len(rows)


def clear_history(adam_id: str | None = None, country_iso: str | None = None) -> int:
    with _conn() as conn:
        if adam_id and country_iso:
            cur = conn.execute(
                f"DELETE FROM {HISTORY_TABLE} WHERE adam_id=? AND country_iso=?",
                (adam_id, country_iso.upper()),
            )
        elif adam_id:
            cur = conn.execute(f"DELETE FROM {HISTORY_TABLE} WHERE adam_id=?", (adam_id,))
        else:
            cur = conn.execute(f"DELETE FROM {HISTORY_TABLE}")
        conn.commit()
        return cur.rowcount
