"""Build and maintain a lightweight full-text search index over vault markdown."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.vault.parser import scan_vault

SEARCHABLE_NOTE_TYPES = {"source", "topic", "entity", "concept", "synthesis"}

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS vault_fts USING fts5(
    title,
    body,
    note_type,
    rel_path,
    topics,
    tokenize='porter unicode61'
);
"""


class VaultIndexer:
    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        self._db_path = vault_path / ".system" / "state" / "search.db"

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.executescript(FTS_SCHEMA)
        return conn

    def rebuild(self) -> int:
        """Full rebuild of the search index. Returns count of indexed notes."""
        conn = self._connect()
        conn.execute("DELETE FROM vault_fts")

        notes = scan_vault(self.vault_path)
        count = 0
        for note in notes:
            if note.note_type not in SEARCHABLE_NOTE_TYPES:
                continue
            try:
                conn.execute(
                    (
                        "INSERT INTO vault_fts "
                        "(title, body, note_type, rel_path, topics) "
                        "VALUES (?, ?, ?, ?, ?)"
                    ),
                    (
                        note.title,
                        note.body[:10000],
                        note.note_type,
                        note.rel_path,
                        ", ".join(note.topics),
                    ),
                )
                count += 1
            except Exception:
                continue

        conn.commit()
        conn.close()
        return count

    def search(self, query: str, limit: int = 15) -> list[dict]:
        conn = self._connect()
        try:
            fts_query = " OR ".join(query.split())
            rows = conn.execute(
                """SELECT title, snippet(vault_fts, 1, '', '', '...', 40) as snippet,
                          note_type, rel_path, bm25(vault_fts) as score
                   FROM vault_fts
                   WHERE vault_fts MATCH ?
                   ORDER BY score
                   LIMIT ?""",
                (fts_query, limit),
            ).fetchall()
        except Exception:
            rows = []

        results = []
        for row in rows:
            results.append(
                {
                    "title": row[0],
                    "snippet": row[1],
                    "type": row[2],
                    "path": row[3],
                }
            )
        conn.close()
        return results
