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
    provider TEXT DEFAULT '',
    external_id TEXT DEFAULT '',
    provider_metadata TEXT DEFAULT '{}',
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

CREATE TABLE IF NOT EXISTS review_surface_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_type TEXT NOT NULL,
    period_key TEXT NOT NULL,
    source_note_path TEXT NOT NULL,
    surfaced_at TEXT NOT NULL,
    reason TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sources_url_hash ON processed_sources(url_hash);
CREATE INDEX IF NOT EXISTS idx_sources_content_hash ON processed_sources(content_hash);
CREATE INDEX IF NOT EXISTS idx_vault_notes_type ON vault_notes(note_type);
CREATE INDEX IF NOT EXISTS idx_review_surface_period
    ON review_surface_history(review_type, period_key);
CREATE INDEX IF NOT EXISTS idx_review_surface_note
    ON review_surface_history(source_note_path, surfaced_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_review_surface_unique
    ON review_surface_history(review_type, period_key, source_note_path);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    normalized_url TEXT DEFAULT '',
    url_hash TEXT NOT NULL,
    canonical_url TEXT DEFAULT '',
    canonical_url_hash TEXT DEFAULT '',
    content_hash TEXT DEFAULT '',
    source_type TEXT DEFAULT '',
    title TEXT DEFAULT '',
    description TEXT DEFAULT '',
    author TEXT DEFAULT '',
    site_name TEXT DEFAULT '',
    language TEXT DEFAULT 'en',
    published_date TEXT DEFAULT '',
    saved_at TEXT,
    metadata_status TEXT DEFAULT 'metadata_only',
    content_status TEXT DEFAULT 'not_fetched',
    brief_status TEXT DEFAULT 'not_started',
    deep_status TEXT DEFAULT 'not_started',
    output_status TEXT DEFAULT 'not_published',
    failure_status TEXT DEFAULT 'none',
    last_failure_reason TEXT DEFAULT '',
    tag_snapshot TEXT DEFAULT '[]',
    provider_snapshot TEXT DEFAULT '{}',
    priority_score REAL DEFAULT 0,
    priority_reasons TEXT DEFAULT '{}',
    priority_policy_version TEXT DEFAULT '',
    priority_computed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_provider_refs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_uid TEXT NOT NULL,
    provider TEXT NOT NULL,
    external_id TEXT DEFAULT '',
    external_url TEXT DEFAULT '',
    external_created_at TEXT,
    external_updated_at TEXT,
    saved_at TEXT,
    title TEXT DEFAULT '',
    metadata TEXT DEFAULT '{}',
    raw_json TEXT DEFAULT '{}',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (source_uid) REFERENCES sources(uid)
);

CREATE TABLE IF NOT EXISTS source_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_uid TEXT NOT NULL,
    tag TEXT NOT NULL,
    normalized_tag TEXT NOT NULL,
    origin TEXT DEFAULT 'provider',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (source_uid) REFERENCES sources(uid)
);

CREATE TABLE IF NOT EXISTS processing_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_uid TEXT NOT NULL UNIQUE,
    source_uid TEXT NOT NULL,
    task_type TEXT NOT NULL,
    mode TEXT DEFAULT 'safe',
    status TEXT DEFAULT 'queued',
    priority_score REAL DEFAULT 0,
    priority_reasons TEXT DEFAULT '{}',
    priority_policy_version TEXT DEFAULT '',
    requested_by TEXT DEFAULT 'system',
    requested_reason TEXT DEFAULT '',
    queued_item_id INTEGER,
    processed_source_id INTEGER,
    run_after TEXT,
    started_at TEXT,
    finished_at TEXT,
    last_error TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (source_uid) REFERENCES sources(uid)
);

CREATE TABLE IF NOT EXISTS processing_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_uid TEXT NOT NULL,
    attempt_number INTEGER DEFAULT 1,
    backend_used TEXT DEFAULT '',
    model_used TEXT DEFAULT '',
    started_at TEXT NOT NULL,
    finished_at TEXT,
    success INTEGER DEFAULT 0,
    error TEXT DEFAULT '',
    error_type TEXT DEFAULT '',
    usage_event_uid TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (job_uid) REFERENCES processing_jobs(job_uid)
);

CREATE TABLE IF NOT EXISTS usage_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_uid TEXT NOT NULL UNIQUE,
    source_uid TEXT DEFAULT '',
    job_uid TEXT DEFAULT '',
    attempt_id INTEGER,
    task_type TEXT DEFAULT '',
    backend TEXT DEFAULT '',
    model TEXT DEFAULT '',
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    estimated_cost REAL DEFAULT 0,
    budget_bucket TEXT DEFAULT 'global',
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_catalog_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_uid TEXT NOT NULL UNIQUE,
    snapshot_path TEXT DEFAULT '',
    source_count INTEGER DEFAULT 0,
    reason TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'New conversation',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    message_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL DEFAULT '',
    tool_calls TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chat_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_catalog_sources_url_hash ON sources(url_hash);
CREATE INDEX IF NOT EXISTS idx_catalog_sources_content_hash ON sources(content_hash);
CREATE INDEX IF NOT EXISTS idx_catalog_sources_type ON sources(source_type);
CREATE INDEX IF NOT EXISTS idx_catalog_sources_status
    ON sources(metadata_status, content_status, brief_status, deep_status);
CREATE INDEX IF NOT EXISTS idx_source_provider_refs_source
    ON source_provider_refs(source_uid);
CREATE INDEX IF NOT EXISTS idx_source_provider_refs_provider
    ON source_provider_refs(provider, external_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_source_provider_refs_unique_external
    ON source_provider_refs(provider, external_id)
    WHERE external_id != '';
CREATE UNIQUE INDEX IF NOT EXISTS idx_source_tags_unique
    ON source_tags(source_uid, normalized_tag, origin);
CREATE INDEX IF NOT EXISTS idx_source_tags_tag ON source_tags(normalized_tag);
CREATE INDEX IF NOT EXISTS idx_processing_jobs_source_status
    ON processing_jobs(source_uid, status);
CREATE INDEX IF NOT EXISTS idx_processing_jobs_status_priority
    ON processing_jobs(status, priority_score DESC, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_processing_attempts_job
    ON processing_attempts(job_uid);
CREATE INDEX IF NOT EXISTS idx_usage_events_source_job
    ON usage_events(source_uid, job_uid);
CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation
    ON chat_messages(conversation_id, created_at);
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
            self._apply_migrations()
        return self._conn

    def _apply_migrations(self) -> None:
        processed_source_columns = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(processed_sources)").fetchall()
        }

        if "provider" not in processed_source_columns:
            self._conn.execute(
                "ALTER TABLE processed_sources ADD COLUMN provider TEXT DEFAULT ''"
            )
        if "external_id" not in processed_source_columns:
            self._conn.execute(
                "ALTER TABLE processed_sources ADD COLUMN external_id TEXT DEFAULT ''"
            )
        if "provider_metadata" not in processed_source_columns:
            self._conn.execute(
                "ALTER TABLE processed_sources ADD COLUMN provider_metadata TEXT DEFAULT '{}'"
            )

        if "raindrop_id" in processed_source_columns:
            self._conn.execute(
                """
                UPDATE processed_sources
                SET provider = CASE
                        WHEN (provider IS NULL OR provider = '') AND raindrop_id IS NOT NULL
                        THEN 'raindrop'
                        ELSE COALESCE(provider, '')
                    END,
                    external_id = CASE
                        WHEN (external_id IS NULL OR external_id = '') AND raindrop_id IS NOT NULL
                        THEN CAST(raindrop_id AS TEXT)
                        ELSE COALESCE(external_id, '')
                    END
                WHERE raindrop_id IS NOT NULL
                  AND (
                    provider IS NULL OR provider = '' OR external_id IS NULL OR external_id = ''
                  )
                """
            )

        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_sources_provider_external_id
                ON processed_sources(provider, external_id)
            """
        )
        self._migrate_source_catalog_tables()
        self._backfill_source_catalog_from_processed_sources()
        self._conn.commit()

    def _migrate_source_catalog_tables(self) -> None:
        self._ensure_columns(
            "sources",
            {
                "normalized_url": "TEXT DEFAULT ''",
                "canonical_url": "TEXT DEFAULT ''",
                "canonical_url_hash": "TEXT DEFAULT ''",
                "content_hash": "TEXT DEFAULT ''",
                "description": "TEXT DEFAULT ''",
                "author": "TEXT DEFAULT ''",
                "site_name": "TEXT DEFAULT ''",
                "language": "TEXT DEFAULT 'en'",
                "published_date": "TEXT DEFAULT ''",
                "saved_at": "TEXT",
                "metadata_status": "TEXT DEFAULT 'metadata_only'",
                "content_status": "TEXT DEFAULT 'not_fetched'",
                "brief_status": "TEXT DEFAULT 'not_started'",
                "deep_status": "TEXT DEFAULT 'not_started'",
                "output_status": "TEXT DEFAULT 'not_published'",
                "failure_status": "TEXT DEFAULT 'none'",
                "last_failure_reason": "TEXT DEFAULT ''",
                "tag_snapshot": "TEXT DEFAULT '[]'",
                "provider_snapshot": "TEXT DEFAULT '{}'",
                "priority_score": "REAL DEFAULT 0",
                "priority_reasons": "TEXT DEFAULT '{}'",
                "priority_policy_version": "TEXT DEFAULT ''",
                "priority_computed_at": "TEXT",
            },
        )
        self._ensure_columns(
            "source_provider_refs",
            {
                "external_url": "TEXT DEFAULT ''",
                "external_created_at": "TEXT",
                "external_updated_at": "TEXT",
                "saved_at": "TEXT",
                "title": "TEXT DEFAULT ''",
                "metadata": "TEXT DEFAULT '{}'",
                "raw_json": "TEXT DEFAULT '{}'",
                "first_seen_at": "TEXT",
                "last_seen_at": "TEXT",
            },
        )
        self._ensure_columns(
            "processing_jobs",
            {
                "priority_score": "REAL DEFAULT 0",
                "priority_reasons": "TEXT DEFAULT '{}'",
                "priority_policy_version": "TEXT DEFAULT ''",
                "requested_by": "TEXT DEFAULT 'system'",
                "requested_reason": "TEXT DEFAULT ''",
                "queued_item_id": "INTEGER",
                "processed_source_id": "INTEGER",
                "run_after": "TEXT",
                "last_error": "TEXT DEFAULT ''",
            },
        )
        self._conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_source_provider_refs_unique_external
                ON source_provider_refs(provider, external_id)
                WHERE external_id != ''
            """
        )
        self._conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_source_tags_unique
                ON source_tags(source_uid, normalized_tag, origin)
            """
        )

    def _backfill_source_catalog_from_processed_sources(self) -> None:
        """Seed the Studio catalog from the compatibility completion ledger.

        Older vaults can have many completed `processed_sources` rows and no
        `sources` rows. This migration creates captured catalog identities for
        those completed rows so Studio can show existing libraries immediately.
        """
        now_expr = "strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')"
        priority_reasons_expr = (
            '\'{"base": 10, "policy_version": "local-studio-v1", '
            '"backfilled_from": "processed_sources"}\''
        )
        self._conn.execute(
            f"""
            INSERT INTO sources (
                uid, url, normalized_url, url_hash, canonical_url, canonical_url_hash,
                content_hash, source_type, title, description, author, site_name,
                language, published_date, saved_at, metadata_status, content_status,
                brief_status, deep_status, output_status, failure_status,
                last_failure_reason, tag_snapshot, provider_snapshot, priority_score,
                priority_reasons, priority_policy_version, priority_computed_at,
                created_at, updated_at
            )
            SELECT
                'src_' || lower(hex(randomblob(16))),
                p.url,
                p.url,
                p.url_hash,
                '',
                '',
                COALESCE(p.content_hash, ''),
                COALESCE(p.source_type, ''),
                COALESCE(p.title, ''),
                '',
                '',
                '',
                'en',
                '',
                NULL,
                CASE WHEN p.status = 'completed' THEN 'captured' ELSE 'metadata_only' END,
                CASE
                    WHEN p.status = 'completed' THEN 'available'
                    WHEN COALESCE(p.error_message, '') != '' THEN 'failed'
                    ELSE 'not_fetched'
                END,
                CASE WHEN p.status = 'completed' THEN 'ready' ELSE 'not_started' END,
                'not_started',
                CASE WHEN p.status = 'completed' THEN 'published' ELSE 'not_published' END,
                CASE WHEN COALESCE(p.error_message, '') != '' THEN 'failed' ELSE 'none' END,
                COALESCE(p.error_message, ''),
                '[]',
                CASE
                    WHEN COALESCE(p.provider, '') != '' THEN
                        json_object(
                            p.provider,
                            json_object(
                                'external_id', COALESCE(p.external_id, ''),
                                'title', COALESCE(p.title, ''),
                                'metadata', json(COALESCE(NULLIF(p.provider_metadata, ''), '{{}}'))
                            )
                        )
                    ELSE '{{}}'
                END,
                10,
                {priority_reasons_expr},
                'local-studio-v1',
                {now_expr},
                COALESCE(p.created_at, {now_expr}),
                COALESCE(p.updated_at, {now_expr})
            FROM processed_sources p
            WHERE NOT EXISTS (
                SELECT 1 FROM sources s WHERE s.url_hash = p.url_hash
            )
            """
        )
        self._conn.execute(
            f"""
            INSERT INTO source_provider_refs (
                source_uid, provider, external_id, external_url, external_created_at,
                external_updated_at, saved_at, title, metadata, raw_json,
                first_seen_at, last_seen_at, created_at, updated_at
            )
            SELECT
                s.uid,
                p.provider,
                COALESCE(p.external_id, ''),
                p.url,
                NULL,
                NULL,
                NULL,
                COALESCE(p.title, ''),
                COALESCE(NULLIF(p.provider_metadata, ''), '{{}}'),
                COALESCE(NULLIF(p.provider_metadata, ''), '{{}}'),
                COALESCE(p.created_at, {now_expr}),
                COALESCE(p.updated_at, {now_expr}),
                COALESCE(p.created_at, {now_expr}),
                COALESCE(p.updated_at, {now_expr})
            FROM processed_sources p
            JOIN sources s ON s.url_hash = p.url_hash
            WHERE COALESCE(p.provider, '') != ''
              AND NOT EXISTS (
                SELECT 1 FROM source_provider_refs r
                WHERE r.source_uid = s.uid
                  AND r.provider = p.provider
                  AND (
                    (COALESCE(p.external_id, '') != '' AND r.external_id = p.external_id)
                    OR (COALESCE(p.external_id, '') = '' AND r.external_url = p.url)
                  )
              )
            """
        )

    def _ensure_columns(self, table: str, columns: dict[str, str]) -> None:
        existing = {
            row["name"] for row in self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for name, definition in columns.items():
            if name not in existing:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        return self.connect()
