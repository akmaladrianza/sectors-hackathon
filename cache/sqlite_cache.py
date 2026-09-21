"""SQLite cache for Sectors API responses.

Keyed on ``(company, period, endpoint)`` so that:
- the same company's data can be cached per reporting period, and
- different endpoints (report, financials, mining overlay, ...) never collide.

``period`` is an application-defined string. For the company-report endpoint
there is no per-period parameter, so the caller uses an "as-of" key (e.g. the
ISO date of the fetch) to represent "the report as it stood on this date".
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache_entries (
    company    TEXT NOT NULL,
    period     TEXT NOT NULL,
    endpoint   TEXT NOT NULL,
    payload    TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (company, period, endpoint)
);
"""


class SQLiteCache:
    """A tiny JSON-blob cache backed by a single SQLite database file."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    def get(self, company: str, period: str, endpoint: str) -> Optional[dict]:
        """Return the cached payload for a key, or ``None`` on a cache miss."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM cache_entries "
                "WHERE company = ? AND period = ? AND endpoint = ?",
                (company, period, endpoint),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def set(self, company: str, period: str, endpoint: str, payload: dict) -> None:
        """Upsert the cached payload for a key."""
        fetched_at = datetime.now(timezone.utc).isoformat()
        blob = json.dumps(payload)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO cache_entries "
                "(company, period, endpoint, payload, fetched_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(company, period, endpoint) DO UPDATE SET "
                "payload = excluded.payload, fetched_at = excluded.fetched_at",
                (company, period, endpoint, blob, fetched_at),
            )

    def clear(self, company: str, period: str, endpoint: str) -> None:
        """Delete a single cache entry (used to force a fresh pull in demos/tests)."""
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM cache_entries "
                "WHERE company = ? AND period = ? AND endpoint = ?",
                (company, period, endpoint),
            )
