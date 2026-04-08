from __future__ import annotations

import json

from app.models.db import ProcessedSource, SyncCursor, VaultNoteMapping
from app.storage.sqlite import Database
from app.utils.dates import iso_now


class SourceRepository:
    def __init__(self, db: Database):
        self._db = db

    def find_by_url_hash(self, url_hash: str) -> ProcessedSource | None:
        row = self._db.conn.execute(
            "SELECT * FROM processed_sources WHERE url_hash = ?", (url_hash,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_processed_source(row)

    def find_by_content_hash(self, content_hash: str) -> ProcessedSource | None:
        if not content_hash:
            return None
        row = self._db.conn.execute(
            "SELECT * FROM processed_sources WHERE content_hash = ?", (content_hash,)
        ).fetchone()
        return self._row_to_processed_source(row) if row else None

    def upsert(self, src: ProcessedSource) -> None:
        now = iso_now()
        self._db.conn.execute(
            """INSERT INTO processed_sources
               (url, url_hash, content_hash, source_type, title,
                source_note_path, raw_capture_path, provider, external_id, provider_metadata,
                status, error_message, retry_count, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(url_hash) DO UPDATE SET
                 url=excluded.url,
                 content_hash=excluded.content_hash,
                 source_type=excluded.source_type,
                 title=excluded.title,
                 source_note_path=excluded.source_note_path,
                 raw_capture_path=excluded.raw_capture_path,
                 provider=excluded.provider,
                 external_id=excluded.external_id,
                 provider_metadata=excluded.provider_metadata,
                 status=excluded.status,
                 error_message=excluded.error_message,
                 retry_count=excluded.retry_count,
                 updated_at=excluded.updated_at
            """,
            (
                src.url,
                src.url_hash,
                src.content_hash,
                src.source_type,
                src.title,
                src.source_note_path,
                src.raw_capture_path,
                src.provider,
                src.external_id,
                json.dumps(src.provider_metadata or {}, sort_keys=True),
                src.status,
                src.error_message,
                src.retry_count,
                now,
                now,
            ),
        )
        self._db.conn.commit()

    def count(self) -> int:
        row = self._db.conn.execute("SELECT COUNT(*) as c FROM processed_sources").fetchone()
        return row["c"] if row else 0

    def all(self) -> list[ProcessedSource]:
        rows = self._db.conn.execute(
            "SELECT * FROM processed_sources ORDER BY created_at DESC"
        ).fetchall()
        return [self._row_to_processed_source(r) for r in rows]

    @staticmethod
    def _row_to_processed_source(row) -> ProcessedSource:
        payload = dict(row)
        metadata = payload.get("provider_metadata", "{}") or "{}"
        if isinstance(metadata, str):
            try:
                payload["provider_metadata"] = json.loads(metadata)
            except json.JSONDecodeError:
                payload["provider_metadata"] = {}
        elif metadata is None:
            payload["provider_metadata"] = {}
        return ProcessedSource(**payload)


class SyncCursorRepository:
    def __init__(self, db: Database):
        self._db = db

    def get(self, connector: str) -> SyncCursor | None:
        row = self._db.conn.execute(
            "SELECT * FROM sync_cursors WHERE connector = ?", (connector,)
        ).fetchone()
        return SyncCursor(**dict(row)) if row else None

    def upsert(self, cursor: SyncCursor) -> None:
        self._db.conn.execute(
            """INSERT INTO sync_cursors (connector, last_sync_at, cursor_value)
               VALUES (?, ?, ?)
               ON CONFLICT(connector) DO UPDATE SET
                 last_sync_at=excluded.last_sync_at,
                 cursor_value=excluded.cursor_value
            """,
            (cursor.connector, cursor.last_sync_at.isoformat(), cursor.cursor_value),
        )
        self._db.conn.commit()


class VaultNoteRepository:
    def __init__(self, db: Database):
        self._db = db

    def upsert(self, mapping: VaultNoteMapping) -> None:
        now = iso_now()
        self._db.conn.execute(
            """INSERT INTO vault_notes
               (note_path, note_type, slug, title, source_url, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(note_path) DO UPDATE SET
                 title=excluded.title,
                 slug=excluded.slug,
                 source_url=excluded.source_url,
                 updated_at=excluded.updated_at
            """,
            (
                mapping.note_path,
                mapping.note_type,
                mapping.slug,
                mapping.title,
                mapping.source_url,
                now,
                now,
            ),
        )
        self._db.conn.commit()

    def find_by_type(self, note_type: str) -> list[VaultNoteMapping]:
        rows = self._db.conn.execute(
            "SELECT * FROM vault_notes WHERE note_type = ?", (note_type,)
        ).fetchall()
        return [VaultNoteMapping(**dict(r)) for r in rows]

    def find_by_slug(self, slug: str) -> VaultNoteMapping | None:
        row = self._db.conn.execute("SELECT * FROM vault_notes WHERE slug = ?", (slug,)).fetchone()
        return VaultNoteMapping(**dict(row)) if row else None

    def all(self) -> list[VaultNoteMapping]:
        rows = self._db.conn.execute(
            "SELECT * FROM vault_notes ORDER BY note_type, title"
        ).fetchall()
        return [VaultNoteMapping(**dict(r)) for r in rows]

    def count_by_type(self) -> dict[str, int]:
        rows = self._db.conn.execute(
            "SELECT note_type, COUNT(*) as c FROM vault_notes GROUP BY note_type"
        ).fetchall()
        return {r["note_type"]: r["c"] for r in rows}
