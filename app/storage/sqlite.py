from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    url_hash TEXT NOT NULL UNIQUE,
    content_hash TEXT DEFAULT '',
    source_type TEXT DEFAULT '',
    title TEXT DEFAULT '',
    source_note_path TEXT DEFAULT '',
    raw_capture_path TEXT DEFAULT '',
    raindrop_id INTEGER,
    status TEXT DEFAULT 'completed',
    error_message TEXT DEFAULT '',
    retry_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_cursors (
    connector TEXT PRIMARY KEY,
    last_sync_at TEXT NOT NULL,
    cursor_value TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS vault_notes (
    note_path TEXT PRIMARY KEY,
    note_type TEXT NOT NULL,
    slug TEXT DEFAULT '',
    title TEXT DEFAULT '',
    source_url TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sources_url_hash ON processed_sources(url_hash);
CREATE INDEX IF NOT EXISTS idx_sources_content_hash ON processed_sources(content_hash);
CREATE INDEX IF NOT EXISTS idx_vault_notes_type ON vault_notes(note_type);
"""


class Database:
    def __init__(self, db_path: Path):
        self._path = db_path
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(SCHEMA)
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        return self.connect()
