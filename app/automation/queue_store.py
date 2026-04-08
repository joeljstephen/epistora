"""Durable queue persistence layer using SQLite."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.automation.models import (
    AutomationRun,
    ItemAttempt,
    QueuedItem,
    QueueItemStatus,
)
from app.storage.sqlite import Database
from app.utils.dates import iso_now

logger = logging.getLogger(__name__)

QUEUE_SCHEMA = """
CREATE TABLE IF NOT EXISTS queued_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connector_id TEXT DEFAULT '',
    external_id TEXT DEFAULT '',
    url TEXT NOT NULL,
    url_hash TEXT NOT NULL,
    title TEXT DEFAULT '',
    source_type TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    saved_at TEXT NOT NULL,
    discovered_at TEXT NOT NULL,
    status TEXT DEFAULT 'discovered',
    attempt_count INTEGER DEFAULT 0,
    next_attempt_at TEXT,
    last_error TEXT DEFAULT '',
    last_error_type TEXT DEFAULT '',
    mode_last_attempted TEXT DEFAULT '',
    backend_last_used TEXT DEFAULT '',
    processed_source_id INTEGER,
    provider_metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS automation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_type TEXT DEFAULT '',
    mode TEXT DEFAULT 'safe',
    started_at TEXT NOT NULL,
    finished_at TEXT,
    items_discovered INTEGER DEFAULT 0,
    items_processed INTEGER DEFAULT 0,
    items_failed INTEGER DEFAULT 0,
    items_skipped INTEGER DEFAULT 0,
    maintenance_ran INTEGER DEFAULT 0,
    error TEXT DEFAULT '',
    summary TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS item_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    queued_item_id INTEGER NOT NULL,
    attempt_number INTEGER DEFAULT 1,
    mode TEXT DEFAULT 'safe',
    backend_used TEXT DEFAULT '',
    started_at TEXT NOT NULL,
    finished_at TEXT,
    success INTEGER DEFAULT 0,
    error TEXT DEFAULT '',
    error_type TEXT DEFAULT '',
    FOREIGN KEY (queued_item_id) REFERENCES queued_items(id)
);

CREATE INDEX IF NOT EXISTS idx_queued_items_status ON queued_items(status);
CREATE INDEX IF NOT EXISTS idx_queued_items_url_hash ON queued_items(url_hash);
CREATE INDEX IF NOT EXISTS idx_queued_items_connector ON queued_items(connector_id, external_id);
CREATE INDEX IF NOT EXISTS idx_queued_items_next_attempt ON queued_items(next_attempt_at);
CREATE INDEX IF NOT EXISTS idx_automation_runs_type ON automation_runs(run_type);
CREATE INDEX IF NOT EXISTS idx_item_attempts_item ON item_attempts(queued_item_id);
"""


def ensure_queue_schema(db: Database) -> None:
    """Create queue tables if they don't exist."""
    db.conn.executescript(QUEUE_SCHEMA)
    db.conn.commit()


class QueueRepository:
    """CRUD operations for the queued_items table."""

    def __init__(self, db: Database):
        self._db = db
        ensure_queue_schema(db)

    def insert(self, item: QueuedItem) -> int:
        """Insert a new queue item and return its ID."""
        now = iso_now()
        cursor = self._db.conn.execute(
            """INSERT INTO queued_items
               (connector_id, external_id, url, url_hash, title, source_type, tags,
                saved_at, discovered_at, status, attempt_count, next_attempt_at,
                last_error, last_error_type, mode_last_attempted, backend_last_used,
                processed_source_id, provider_metadata, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item.connector_id,
                item.external_id,
                item.url,
                item.url_hash,
                item.title,
                item.source_type,
                item.tags if isinstance(item.tags, str) else json.dumps(item.tags),
                item.saved_at.isoformat(),
                item.discovered_at.isoformat(),
                item.status,
                item.attempt_count,
                item.next_attempt_at.isoformat() if item.next_attempt_at else None,
                item.last_error,
                item.last_error_type,
                item.mode_last_attempted,
                item.backend_last_used,
                item.processed_source_id,
                json.dumps(item.provider_metadata or {}),
                now,
                now,
            ),
        )
        self._db.conn.commit()
        return cursor.lastrowid

    def find_by_url_hash(self, url_hash: str) -> QueuedItem | None:
        """Find a queue item by URL hash."""
        row = self._db.conn.execute(
            "SELECT * FROM queued_items WHERE url_hash = ?", (url_hash,)
        ).fetchone()
        return self._row_to_item(row) if row else None

    def find_by_connector_external(
        self, connector_id: str, external_id: str
    ) -> QueuedItem | None:
        """Find a queue item by connector and external ID."""
        row = self._db.conn.execute(
            "SELECT * FROM queued_items WHERE connector_id = ? AND external_id = ?",
            (connector_id, external_id),
        ).fetchone()
        return self._row_to_item(row) if row else None

    def get_pending(
        self,
        limit: int = 10,
        *,
        include_retryable: bool = False,
        connector_id: str | None = None,
    ) -> list[QueuedItem]:
        """Get items ready for processing."""
        now = datetime.now(timezone.utc).isoformat()
        statuses = [QueueItemStatus.DISCOVERED]
        if include_retryable:
            statuses.append(QueueItemStatus.RETRYABLE_FAILED)

        placeholders = ",".join("?" for _ in statuses)
        query = f"""
            SELECT * FROM queued_items
            WHERE status IN ({placeholders})
              AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
        """
        params: list = list(statuses) + [now]

        if connector_id:
            query += " AND connector_id = ?"
            params.append(connector_id)

        query += " ORDER BY saved_at ASC LIMIT ?"
        params.append(limit)

        rows = self._db.conn.execute(query, params).fetchall()
        return [self._row_to_item(r) for r in rows]

    def get_retryable_failed(self, limit: int = 50) -> list[QueuedItem]:
        """Get all retryable failed items."""
        rows = self._db.conn.execute(
            """SELECT * FROM queued_items
               WHERE status = ?
               ORDER BY next_attempt_at ASC NULLS FIRST
               LIMIT ?""",
            (QueueItemStatus.RETRYABLE_FAILED, limit),
        ).fetchall()
        return [self._row_to_item(r) for r in rows]

    def update_status(
        self,
        item_id: int,
        status: str,
        *,
        error: str = "",
        error_type: str = "",
        mode: str = "",
        backend: str = "",
        processed_source_id: int | None = None,
        next_attempt_at: datetime | None = None,
    ) -> None:
        """Update the status and metadata of a queue item."""
        now = iso_now()
        self._db.conn.execute(
            """UPDATE queued_items SET
                 status = ?,
                 last_error = ?,
                 last_error_type = ?,
                 mode_last_attempted = CASE WHEN ? != '' THEN ? ELSE mode_last_attempted END,
                 backend_last_used = CASE WHEN ? != '' THEN ? ELSE backend_last_used END,
                 processed_source_id = COALESCE(?, processed_source_id),
                 next_attempt_at = ?,
                 attempt_count = attempt_count + 1,
                 updated_at = ?
               WHERE id = ?""",
            (
                status,
                error,
                error_type,
                mode, mode,
                backend, backend,
                processed_source_id,
                next_attempt_at.isoformat() if next_attempt_at else None,
                now,
                item_id,
            ),
        )
        self._db.conn.commit()

    def mark_processing(self, item_id: int) -> None:
        """Mark an item as currently being processed."""
        now = iso_now()
        self._db.conn.execute(
            "UPDATE queued_items SET status = ?, updated_at = ? WHERE id = ?",
            (QueueItemStatus.PROCESSING, now, item_id),
        )
        self._db.conn.commit()

    def count_by_status(self) -> dict[str, int]:
        """Return counts of items grouped by status."""
        rows = self._db.conn.execute(
            "SELECT status, COUNT(*) as c FROM queued_items GROUP BY status"
        ).fetchall()
        return {r["status"]: r["c"] for r in rows}

    def count_completed_today(self, mode: str = "deep") -> int:
        """Count items completed with a given mode today."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        row = self._db.conn.execute(
            """SELECT COUNT(*) as c FROM queued_items
               WHERE status = ? AND mode_last_attempted = ?
               AND date(updated_at) = ?""",
            (QueueItemStatus.COMPLETED, mode, today),
        ).fetchone()
        return row["c"] if row else 0

    def reset_stale_processing(self, max_age_minutes: int = 30) -> int:
        """Reset items stuck in 'processing' status back to 'discovered'."""
        from app.utils.dates import utcnow

        cutoff = utcnow().isoformat()
        # Simple: if processing for > max_age_minutes, reset
        cursor = self._db.conn.execute(
            """UPDATE queued_items SET status = ?, updated_at = ?
               WHERE status = ?
               AND datetime(updated_at, '+' || ? || ' minutes') < datetime(?)""",
            (
                QueueItemStatus.DISCOVERED,
                iso_now(),
                QueueItemStatus.PROCESSING,
                str(max_age_minutes),
                cutoff,
            ),
        )
        self._db.conn.commit()
        return cursor.rowcount

    @staticmethod
    def _row_to_item(row) -> QueuedItem:
        payload = dict(row)
        metadata = payload.get("provider_metadata", "{}") or "{}"
        if isinstance(metadata, str):
            try:
                payload["provider_metadata"] = json.loads(metadata)
            except json.JSONDecodeError:
                payload["provider_metadata"] = {}
        # Handle boolean-like fields
        for dt_field in ("saved_at", "discovered_at", "created_at", "updated_at"):
            val = payload.get(dt_field)
            if isinstance(val, str):
                try:
                    payload[dt_field] = datetime.fromisoformat(val)
                except (ValueError, TypeError):
                    pass
        nxt = payload.get("next_attempt_at")
        if isinstance(nxt, str) and nxt:
            try:
                payload["next_attempt_at"] = datetime.fromisoformat(nxt)
            except (ValueError, TypeError):
                payload["next_attempt_at"] = None
        elif nxt is None:
            payload["next_attempt_at"] = None
        return QueuedItem(**payload)


class AutomationRunRepository:
    """CRUD for automation_runs table."""

    def __init__(self, db: Database):
        self._db = db
        ensure_queue_schema(db)

    def insert(self, run: AutomationRun) -> int:
        cursor = self._db.conn.execute(
            """INSERT INTO automation_runs
               (run_type, mode, started_at, finished_at, items_discovered,
                items_processed, items_failed, items_skipped,
                maintenance_ran, error, summary)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run.run_type,
                run.mode,
                run.started_at.isoformat(),
                run.finished_at.isoformat() if run.finished_at else None,
                run.items_discovered,
                run.items_processed,
                run.items_failed,
                run.items_skipped,
                int(run.maintenance_ran),
                run.error,
                run.summary,
            ),
        )
        self._db.conn.commit()
        return cursor.lastrowid

    def update(self, run_id: int, run: AutomationRun) -> None:
        self._db.conn.execute(
            """UPDATE automation_runs SET
                 finished_at = ?, items_discovered = ?, items_processed = ?,
                 items_failed = ?, items_skipped = ?, maintenance_ran = ?,
                 error = ?, summary = ?
               WHERE id = ?""",
            (
                run.finished_at.isoformat() if run.finished_at else None,
                run.items_discovered,
                run.items_processed,
                run.items_failed,
                run.items_skipped,
                int(run.maintenance_ran),
                run.error,
                run.summary,
                run_id,
            ),
        )
        self._db.conn.commit()

    def latest(self, run_type: str | None = None) -> AutomationRun | None:
        if run_type:
            row = self._db.conn.execute(
                "SELECT * FROM automation_runs WHERE run_type = ? ORDER BY id DESC LIMIT 1",
                (run_type,),
            ).fetchone()
        else:
            row = self._db.conn.execute(
                "SELECT * FROM automation_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        return self._row_to_run(row)

    @staticmethod
    def _row_to_run(row) -> AutomationRun:
        payload = dict(row)
        payload["maintenance_ran"] = bool(payload.get("maintenance_ran", 0))
        for dt_field in ("started_at", "finished_at"):
            val = payload.get(dt_field)
            if isinstance(val, str) and val:
                try:
                    payload[dt_field] = datetime.fromisoformat(val)
                except (ValueError, TypeError):
                    pass
            elif val is None and dt_field == "finished_at":
                payload[dt_field] = None
        return AutomationRun(**payload)


class ItemAttemptRepository:
    """CRUD for item_attempts table."""

    def __init__(self, db: Database):
        self._db = db
        ensure_queue_schema(db)

    def insert(self, attempt: ItemAttempt) -> int:
        cursor = self._db.conn.execute(
            """INSERT INTO item_attempts
               (queued_item_id, attempt_number, mode, backend_used,
                started_at, finished_at, success, error, error_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                attempt.queued_item_id,
                attempt.attempt_number,
                attempt.mode,
                attempt.backend_used,
                attempt.started_at.isoformat(),
                attempt.finished_at.isoformat() if attempt.finished_at else None,
                int(attempt.success),
                attempt.error,
                attempt.error_type,
            ),
        )
        self._db.conn.commit()
        return cursor.lastrowid

    def for_item(self, queued_item_id: int) -> list[ItemAttempt]:
        rows = self._db.conn.execute(
            "SELECT * FROM item_attempts WHERE queued_item_id = ? ORDER BY attempt_number",
            (queued_item_id,),
        ).fetchall()
        return [self._row_to_attempt(r) for r in rows]

    @staticmethod
    def _row_to_attempt(row) -> ItemAttempt:
        payload = dict(row)
        payload["success"] = bool(payload.get("success", 0))
        for dt_field in ("started_at", "finished_at"):
            val = payload.get(dt_field)
            if isinstance(val, str) and val:
                try:
                    payload[dt_field] = datetime.fromisoformat(val)
                except (ValueError, TypeError):
                    pass
            elif val is None and dt_field == "finished_at":
                payload[dt_field] = None
        return ItemAttempt(**payload)
