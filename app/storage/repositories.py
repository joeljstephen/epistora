from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models.db import (
    CatalogSource,
    ProcessedSource,
    ProcessingAttempt,
    ProcessingJob,
    SourceCatalogSnapshot,
    SourceProviderRef,
    SourceTag,
    SourceTagOrigin,
    SyncCursor,
    UsageEvent,
    VaultNoteMapping,
)
from app.storage.sqlite import Database
from app.utils.dates import iso_now
from app.utils.hashing import normalize_url, url_hash

PRIORITY_POLICY_VERSION = "local-studio-v1"


def normalize_source_tag(tag: str) -> str:
    """Normalize catalog tags for stable matching while keeping display text separately."""
    cleaned = re.sub(r"\s+", " ", (tag or "").strip().lstrip("#")).strip()
    return cleaned.lower()


def _json_value(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def _max_status(existing: str, incoming: str, order: list[str]) -> str:
    try:
        return order[max(order.index(existing), order.index(incoming))]
    except ValueError:
        return incoming or existing


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

    def find_by_id(self, source_id: int) -> ProcessedSource | None:
        row = self._db.conn.execute(
            "SELECT * FROM processed_sources WHERE id = ?", (source_id,)
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


class SourceCatalogRepository:
    """Repository for Studio source catalog metadata and source-linked jobs."""

    def __init__(self, db: Database):
        self._db = db

    def upsert_source(self, source: CatalogSource) -> CatalogSource:
        """Create or update a metadata catalog source by URL/content identity."""
        now = iso_now()
        prepared = self._prepare_source(source)
        existing = self.find_by_url_hash(prepared.url_hash)
        if existing is None and prepared.content_hash:
            existing = self.find_by_content_hash(prepared.content_hash)

        if existing is None:
            prepared.uid = prepared.uid or f"src_{uuid.uuid4().hex}"
            self._db.conn.execute(
                """INSERT INTO sources
                   (uid, url, normalized_url, url_hash, canonical_url, canonical_url_hash,
                    content_hash, source_type, title, description, author, site_name,
                    language, published_date, saved_at, metadata_status, content_status,
                    brief_status, deep_status, output_status, failure_status,
                    last_failure_reason, tag_snapshot, provider_snapshot, priority_score,
                    priority_reasons, priority_policy_version, priority_computed_at,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                           ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                self._source_values(prepared, now, now),
            )
            self._db.conn.commit()
            return self.get_source(prepared.uid) or prepared

        merged = self._merge_source(existing, prepared)
        merged.updated_at = prepared.updated_at
        self._db.conn.execute(
            """UPDATE sources SET
                 url = ?, normalized_url = ?, url_hash = ?, canonical_url = ?,
                 canonical_url_hash = ?, content_hash = ?, source_type = ?, title = ?,
                 description = ?, author = ?, site_name = ?, language = ?,
                 published_date = ?, saved_at = ?, metadata_status = ?, content_status = ?,
                 brief_status = ?, deep_status = ?, output_status = ?, failure_status = ?,
                 last_failure_reason = ?, tag_snapshot = ?, provider_snapshot = ?,
                 priority_score = ?, priority_reasons = ?, priority_policy_version = ?,
                 priority_computed_at = ?, updated_at = ?
               WHERE uid = ?""",
            (
                merged.url,
                merged.normalized_url,
                merged.url_hash,
                merged.canonical_url,
                merged.canonical_url_hash,
                merged.content_hash,
                merged.source_type,
                merged.title,
                merged.description,
                merged.author,
                merged.site_name,
                merged.language,
                merged.published_date,
                merged.saved_at.isoformat() if merged.saved_at else None,
                merged.metadata_status,
                merged.content_status,
                merged.brief_status,
                merged.deep_status,
                merged.output_status,
                merged.failure_status,
                merged.last_failure_reason,
                json.dumps(merged.tag_snapshot, sort_keys=True),
                json.dumps(merged.provider_snapshot, sort_keys=True),
                merged.priority_score,
                json.dumps(merged.priority_reasons, sort_keys=True),
                merged.priority_policy_version,
                (
                    merged.priority_computed_at.isoformat()
                    if merged.priority_computed_at
                    else None
                ),
                now,
                merged.uid,
            ),
        )
        self._db.conn.commit()
        return self.get_source(merged.uid) or merged

    def get_source(self, source_uid: str) -> CatalogSource | None:
        row = self._db.conn.execute("SELECT * FROM sources WHERE uid = ?", (source_uid,)).fetchone()
        return self._row_to_source(row) if row else None

    def find_by_url_hash(self, hash_value: str) -> CatalogSource | None:
        row = self._db.conn.execute(
            "SELECT * FROM sources WHERE url_hash = ? ORDER BY id ASC LIMIT 1",
            (hash_value,),
        ).fetchone()
        return self._row_to_source(row) if row else None

    def find_by_content_hash(self, hash_value: str) -> CatalogSource | None:
        if not hash_value:
            return None
        row = self._db.conn.execute(
            "SELECT * FROM sources WHERE content_hash = ? ORDER BY id ASC LIMIT 1",
            (hash_value,),
        ).fetchone()
        return self._row_to_source(row) if row else None

    def attach_provider_ref(self, ref: SourceProviderRef) -> SourceProviderRef:
        """Attach or update a provider sighting without duplicating external refs."""
        self._require_source(ref.source_uid)
        now = iso_now()
        existing = None
        if ref.external_id:
            existing = self._db.conn.execute(
                """SELECT * FROM source_provider_refs
                   WHERE provider = ? AND external_id = ?
                   LIMIT 1""",
                (ref.provider, ref.external_id),
            ).fetchone()
        if existing is None and ref.external_url:
            existing = self._db.conn.execute(
                """SELECT * FROM source_provider_refs
                   WHERE provider = ? AND source_uid = ? AND external_url = ?
                   LIMIT 1""",
                (ref.provider, ref.source_uid, ref.external_url),
            ).fetchone()

        if existing:
            existing_ref = self._row_to_provider_ref(existing)
            self._db.conn.execute(
                """UPDATE source_provider_refs SET
                     external_url = ?, external_created_at = ?, external_updated_at = ?,
                     saved_at = ?, title = ?, metadata = ?, raw_json = ?,
                     last_seen_at = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    ref.external_url or existing_ref.external_url,
                    self._dt(ref.external_created_at) or self._dt(existing_ref.external_created_at),
                    self._dt(ref.external_updated_at) or self._dt(existing_ref.external_updated_at),
                    self._dt(ref.saved_at) or self._dt(existing_ref.saved_at),
                    ref.title or existing_ref.title,
                    json.dumps(ref.metadata or existing_ref.metadata, sort_keys=True),
                    json.dumps(ref.raw_json or existing_ref.raw_json, sort_keys=True),
                    now,
                    now,
                    existing_ref.id,
                ),
            )
            self._db.conn.commit()
            self._refresh_provider_snapshot(existing_ref.source_uid)
            return self.get_provider_ref(existing_ref.id or 0) or existing_ref

        self._db.conn.execute(
            """INSERT INTO source_provider_refs
               (source_uid, provider, external_id, external_url, external_created_at,
                external_updated_at, saved_at, title, metadata, raw_json,
                first_seen_at, last_seen_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ref.source_uid,
                ref.provider,
                ref.external_id,
                ref.external_url,
                self._dt(ref.external_created_at),
                self._dt(ref.external_updated_at),
                self._dt(ref.saved_at),
                ref.title,
                json.dumps(ref.metadata, sort_keys=True),
                json.dumps(ref.raw_json, sort_keys=True),
                now,
                now,
                now,
                now,
            ),
        )
        ref_id = self._db.conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        self._db.conn.commit()
        self._refresh_provider_snapshot(ref.source_uid)
        return self.get_provider_ref(ref_id) or ref

    def get_provider_ref(self, ref_id: int) -> SourceProviderRef | None:
        row = self._db.conn.execute(
            "SELECT * FROM source_provider_refs WHERE id = ?", (ref_id,)
        ).fetchone()
        return self._row_to_provider_ref(row) if row else None

    def provider_refs_for_source(self, source_uid: str) -> list[SourceProviderRef]:
        rows = self._db.conn.execute(
            "SELECT * FROM source_provider_refs WHERE source_uid = ? ORDER BY provider, id",
            (source_uid,),
        ).fetchall()
        return [self._row_to_provider_ref(row) for row in rows]

    def sync_tags(
        self,
        source_uid: str,
        tags: list[str],
        *,
        origin: str = SourceTagOrigin.PROVIDER,
    ) -> list[SourceTag]:
        self._require_source(source_uid)
        now = iso_now()
        normalized: dict[str, str] = {}
        for raw in tags:
            norm = normalize_source_tag(raw)
            if norm:
                normalized.setdefault(norm, raw.strip().lstrip("#"))

        self._db.conn.execute(
            """DELETE FROM source_tags
               WHERE source_uid = ? AND origin = ?
                 AND normalized_tag NOT IN (%s)"""
            % ",".join("?" for _ in normalized)
            if normalized
            else "DELETE FROM source_tags WHERE source_uid = ? AND origin = ?",
            (source_uid, origin, *normalized.keys()) if normalized else (source_uid, origin),
        )
        for norm, display in normalized.items():
            self._db.conn.execute(
                """INSERT INTO source_tags
                   (source_uid, tag, normalized_tag, origin, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source_uid, normalized_tag, origin) DO UPDATE SET
                     tag = excluded.tag,
                     updated_at = excluded.updated_at""",
                (source_uid, display, norm, origin, now, now),
            )
        self._db.conn.commit()
        self._refresh_tag_snapshot(source_uid)
        self.store_priority_score(source_uid)
        return self.tags_for_source(source_uid)

    def tags_for_source(self, source_uid: str) -> list[SourceTag]:
        rows = self._db.conn.execute(
            "SELECT * FROM source_tags WHERE source_uid = ? ORDER BY normalized_tag, origin",
            (source_uid,),
        ).fetchall()
        return [SourceTag(**dict(row)) for row in rows]

    def list_sources(
        self,
        *,
        limit: int = 50,
        query: str = "",
        metadata_only: bool = False,
        source_type: str = "",
        display_state: str = "",
        provider: str = "",
        tag: str = "",
    ) -> list[CatalogSource]:
        sql = "SELECT s.* FROM sources s"
        clauses: list[str] = []
        params: list[Any] = []
        if provider:
            sql += (
                " INNER JOIN source_provider_refs r ON r.source_uid = s.uid AND r.provider = ?"
            )
            params.append(provider)
        if tag:
            sql += (
                " INNER JOIN source_tags t ON t.source_uid = s.uid AND t.normalized_tag = ?"
            )
            params.append(tag.lower())
        if metadata_only:
            clauses.append("s.metadata_status = ? AND s.content_status = ?")
            params.extend(["metadata_only", "not_fetched"])
        if source_type:
            clauses.append("s.source_type = ?")
            params.append(source_type)
        if display_state:
            state_clause, state_params = self._display_state_clauses(display_state)
            if state_clause:
                clauses.append(state_clause)
                params.extend(state_params)
        if query:
            like = f"%{query.lower()}%"
            clauses.append(
                "(lower(s.title) LIKE ? OR lower(s.url) LIKE ? OR lower(s.description) LIKE ?)"
            )
            params.extend([like, like, like])
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += (
            " GROUP BY s.id"
            " ORDER BY s.priority_score DESC, s.saved_at DESC, s.created_at DESC LIMIT ?"
        )
        params.append(limit)
        rows = self._db.conn.execute(sql, params).fetchall()
        return [self._row_to_source(row) for row in rows]

    @staticmethod
    def _display_state_clauses(display_state: str) -> tuple[str, list[Any]]:
        """Translate a derived display state into SQL filters.

        Display states are derived in `derive_display_state`; we mirror the
        precedence here so filters return the same set the UI shows.
        """
        from app.models.source_lifecycle import display_state_clause

        clause, params = display_state_clause(display_state)
        return clause, list(params)

    def search_sources(self, query: str, *, limit: int = 50) -> list[CatalogSource]:
        return self.list_sources(limit=limit, query=query)

    def update_lifecycle(
        self,
        source_uid: str,
        *,
        metadata_status: str | None = None,
        content_status: str | None = None,
        brief_status: str | None = None,
        deep_status: str | None = None,
        output_status: str | None = None,
        failure_status: str | None = None,
        last_failure_reason: str | None = None,
        canonical_url: str | None = None,
        content_hash: str | None = None,
        title: str | None = None,
        source_type: str | None = None,
    ) -> CatalogSource:
        source = self._require_source(source_uid)
        values = {
            "metadata_status": metadata_status or source.metadata_status,
            "content_status": content_status or source.content_status,
            "brief_status": brief_status or source.brief_status,
            "deep_status": deep_status or source.deep_status,
            "output_status": output_status or source.output_status,
            "failure_status": failure_status or source.failure_status,
            "last_failure_reason": (
                source.last_failure_reason if last_failure_reason is None else last_failure_reason
            ),
            "canonical_url": canonical_url or source.canonical_url,
            "canonical_url_hash": (
                url_hash(canonical_url) if canonical_url else source.canonical_url_hash
            ),
            "content_hash": content_hash or source.content_hash,
            "title": title or source.title,
            "source_type": source_type or source.source_type,
            "updated_at": iso_now(),
            "uid": source_uid,
        }
        self._db.conn.execute(
            """UPDATE sources SET
                 metadata_status = ?, content_status = ?, brief_status = ?,
                 deep_status = ?, output_status = ?, failure_status = ?,
                 last_failure_reason = ?, canonical_url = ?, canonical_url_hash = ?,
                 content_hash = ?, title = ?, source_type = ?, updated_at = ?
               WHERE uid = ?""",
            (
                values["metadata_status"],
                values["content_status"],
                values["brief_status"],
                values["deep_status"],
                values["output_status"],
                values["failure_status"],
                values["last_failure_reason"],
                values["canonical_url"],
                values["canonical_url_hash"],
                values["content_hash"],
                values["title"],
                values["source_type"],
                values["updated_at"],
                values["uid"],
            ),
        )
        self._db.conn.commit()
        return self.get_source(source_uid) or source

    def store_priority_score(
        self,
        source_uid: str,
        *,
        requested_by: str = "system",
        requested_reason: str = "",
    ) -> tuple[float, dict[str, Any]]:
        source = self.get_source(source_uid)
        if source is None:
            raise ValueError(f"Source '{source_uid}' does not exist")
        score, reasons = self.compute_priority(
            source,
            requested_by=requested_by,
            requested_reason=requested_reason,
        )
        now = iso_now()
        self._db.conn.execute(
            """UPDATE sources SET priority_score = ?, priority_reasons = ?,
                 priority_policy_version = ?, priority_computed_at = ?, updated_at = ?
               WHERE uid = ?""",
            (
                score,
                json.dumps(reasons, sort_keys=True),
                PRIORITY_POLICY_VERSION,
                now,
                now,
                source_uid,
            ),
        )
        self._db.conn.commit()
        return score, reasons

    def enqueue_processing_job(
        self,
        *,
        source_uid: str,
        task_type: str,
        mode: str = "safe",
        requested_by: str = "system",
        requested_reason: str = "",
        queued_item_id: int | None = None,
        run_after: datetime | None = None,
    ) -> ProcessingJob:
        source = self._require_source(source_uid)
        existing = self._db.conn.execute(
            """SELECT * FROM processing_jobs
               WHERE source_uid = ? AND task_type = ? AND mode = ?
                 AND status IN ('queued', 'running')
               ORDER BY id DESC LIMIT 1""",
            (source_uid, task_type, mode),
        ).fetchone()
        if existing:
            return self._row_to_job(existing)

        score, reasons = self.compute_priority(
            source,
            requested_by=requested_by,
            requested_reason=requested_reason,
            task_type=task_type,
        )
        job_uid = f"job_{uuid.uuid4().hex}"
        now = iso_now()
        self._db.conn.execute(
            """INSERT INTO processing_jobs
               (job_uid, source_uid, task_type, mode, status, priority_score,
                priority_reasons, priority_policy_version, requested_by,
                requested_reason, queued_item_id, run_after, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_uid,
                source_uid,
                task_type,
                mode,
                "queued",
                score,
                json.dumps(reasons, sort_keys=True),
                PRIORITY_POLICY_VERSION,
                requested_by,
                requested_reason,
                queued_item_id,
                run_after.isoformat() if run_after else None,
                now,
                now,
            ),
        )
        self._db.conn.commit()
        row = self._db.conn.execute(
            "SELECT * FROM processing_jobs WHERE job_uid = ?", (job_uid,)
        ).fetchone()
        return self._row_to_job(row)

    def get_processing_job(self, job_uid: str) -> ProcessingJob | None:
        row = self._db.conn.execute(
            "SELECT * FROM processing_jobs WHERE job_uid = ?", (job_uid,)
        ).fetchone()
        return self._row_to_job(row) if row else None

    def latest_jobs_for_source(
        self,
        source_uid: str,
        *,
        limit: int = 10,
    ) -> list[ProcessingJob]:
        rows = self._db.conn.execute(
            """SELECT * FROM processing_jobs
               WHERE source_uid = ?
               ORDER BY created_at DESC, id DESC
               LIMIT ?""",
            (source_uid, limit),
        ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def list_processing_jobs(
        self,
        *,
        limit: int = 50,
        status: str = "",
    ) -> list[ProcessingJob]:
        sql = "SELECT * FROM processing_jobs"
        params: list[Any] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = self._db.conn.execute(sql, params).fetchall()
        return [self._row_to_job(row) for row in rows]

    def next_processing_jobs(self, *, limit: int = 5) -> list[ProcessingJob]:
        now = iso_now()
        rows = self._db.conn.execute(
            """SELECT * FROM processing_jobs
               WHERE status = 'queued'
                 AND (run_after IS NULL OR run_after <= ?)
               ORDER BY priority_score DESC, created_at ASC
               LIMIT ?""",
            (now, limit),
        ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def mark_processing_job_running(self, job_uid: str) -> ProcessingJob:
        now = iso_now()
        self._db.conn.execute(
            """UPDATE processing_jobs SET status = 'running', started_at = ?,
                 finished_at = NULL, last_error = '', updated_at = ?
               WHERE job_uid = ?""",
            (now, now, job_uid),
        )
        self._db.conn.commit()
        job = self.get_processing_job(job_uid)
        if job is None:
            raise ValueError(f"Processing job '{job_uid}' does not exist")
        return job

    def mark_processing_job_completed(
        self,
        job_uid: str,
        *,
        processed_source_id: int | None = None,
        queued_item_id: int | None = None,
    ) -> ProcessingJob:
        now = iso_now()
        self._db.conn.execute(
            """UPDATE processing_jobs SET status = 'completed', finished_at = ?,
                 last_error = '', processed_source_id = COALESCE(?, processed_source_id),
                 queued_item_id = COALESCE(?, queued_item_id), updated_at = ?
               WHERE job_uid = ?""",
            (now, processed_source_id, queued_item_id, now, job_uid),
        )
        self._db.conn.commit()
        job = self.get_processing_job(job_uid)
        if job is None:
            raise ValueError(f"Processing job '{job_uid}' does not exist")
        return job

    def mark_processing_job_failed(
        self,
        job_uid: str,
        *,
        error: str,
        queued_item_id: int | None = None,
    ) -> ProcessingJob:
        now = iso_now()
        self._db.conn.execute(
            """UPDATE processing_jobs SET status = 'failed', finished_at = ?,
                 last_error = ?, queued_item_id = COALESCE(?, queued_item_id),
                 updated_at = ?
               WHERE job_uid = ?""",
            (now, error[:500], queued_item_id, now, job_uid),
        )
        self._db.conn.commit()
        job = self.get_processing_job(job_uid)
        if job is None:
            raise ValueError(f"Processing job '{job_uid}' does not exist")
        return job

    def set_job_queued_item(self, job_uid: str, queued_item_id: int) -> None:
        self._db.conn.execute(
            "UPDATE processing_jobs SET queued_item_id = ?, updated_at = ? WHERE job_uid = ?",
            (queued_item_id, iso_now(), job_uid),
        )
        self._db.conn.commit()

    def processing_attempt_count(self, job_uid: str) -> int:
        row = self._db.conn.execute(
            "SELECT COUNT(*) AS c FROM processing_attempts WHERE job_uid = ?",
            (job_uid,),
        ).fetchone()
        return int(row["c"] if row else 0)

    def record_processing_attempt(self, attempt: ProcessingAttempt) -> ProcessingAttempt:
        now = iso_now()
        self._db.conn.execute(
            """INSERT INTO processing_attempts
               (job_uid, attempt_number, backend_used, model_used, started_at,
                finished_at, success, error, error_type, usage_event_uid, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                attempt.job_uid,
                attempt.attempt_number,
                attempt.backend_used,
                attempt.model_used,
                attempt.started_at.isoformat(),
                attempt.finished_at.isoformat() if attempt.finished_at else None,
                int(attempt.success),
                attempt.error,
                attempt.error_type,
                attempt.usage_event_uid,
                now,
            ),
        )
        attempt_id = self._db.conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        self._db.conn.commit()
        row = self._db.conn.execute(
            "SELECT * FROM processing_attempts WHERE id = ?", (attempt_id,)
        ).fetchone()
        return self._row_to_processing_attempt(row)

    def export_snapshot(self, snapshot_path: Path, *, reason: str = "") -> SourceCatalogSnapshot:
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        sources = self.list_sources(limit=1_000_000)
        with snapshot_path.open("w", encoding="utf-8") as fh:
            for source in sources:
                payload = {
                    "record_type": "source_catalog_snapshot_v1",
                    "source": source.model_dump(mode="json"),
                    "provider_refs": [
                        ref.model_dump(mode="json")
                        for ref in self.provider_refs_for_source(source.uid)
                    ],
                    "tags": [
                        tag.model_dump(mode="json")
                        for tag in self.tags_for_source(source.uid)
                    ],
                }
                fh.write(json.dumps(payload, sort_keys=True) + "\n")

        snapshot_uid = f"snap_{uuid.uuid4().hex}"
        now = iso_now()
        self._db.conn.execute(
            """INSERT INTO source_catalog_snapshots
               (snapshot_uid, snapshot_path, source_count, reason, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (snapshot_uid, str(snapshot_path), len(sources), reason, now),
        )
        self._db.conn.commit()
        row = self._db.conn.execute(
            "SELECT * FROM source_catalog_snapshots WHERE snapshot_uid = ?",
            (snapshot_uid,),
        ).fetchone()
        return SourceCatalogSnapshot(**dict(row))

    def import_snapshot(self, snapshot_path: Path) -> int:
        imported = 0
        with snapshot_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                payload = json.loads(line)
                if payload.get("record_type") != "source_catalog_snapshot_v1":
                    continue
                source = CatalogSource(**payload["source"])
                restored = self.upsert_source(source)
                for ref_payload in payload.get("provider_refs", []):
                    ref_payload["source_uid"] = restored.uid
                    self.attach_provider_ref(SourceProviderRef(**ref_payload))
                tags_by_origin: dict[str, list[str]] = {}
                for tag_payload in payload.get("tags", []):
                    tags_by_origin.setdefault(
                        tag_payload.get("origin") or SourceTagOrigin.PROVIDER,
                        [],
                    ).append(tag_payload.get("tag") or "")
                for origin, tags in tags_by_origin.items():
                    self.sync_tags(restored.uid, tags, origin=origin)
                imported += 1
        return imported

    def record_usage_event(self, event: UsageEvent) -> UsageEvent:
        event_uid = event.event_uid or f"use_{uuid.uuid4().hex}"
        now = iso_now()
        self._db.conn.execute(
            """INSERT INTO usage_events
               (event_uid, source_uid, job_uid, attempt_id, task_type, backend, model,
                input_tokens, output_tokens, estimated_cost, budget_bucket, metadata, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_uid,
                event.source_uid,
                event.job_uid,
                event.attempt_id,
                event.task_type,
                event.backend,
                event.model,
                event.input_tokens,
                event.output_tokens,
                event.estimated_cost,
                event.budget_bucket,
                json.dumps(event.metadata, sort_keys=True),
                now,
            ),
        )
        self._db.conn.commit()
        row = self._db.conn.execute(
            "SELECT * FROM usage_events WHERE event_uid = ?", (event_uid,)
        ).fetchone()
        return self._row_to_usage_event(row)

    def compute_priority(
        self,
        source: CatalogSource,
        *,
        requested_by: str = "system",
        requested_reason: str = "",
        task_type: str = "",
    ) -> tuple[float, dict[str, Any]]:
        reasons: dict[str, Any] = {
            "policy_version": PRIORITY_POLICY_VERSION,
            "base": 10,
        }
        score = 10.0
        requester = requested_by.lower()
        if requester in {"user", "manual", "studio"}:
            score += 50
            reasons["explicit_request"] = 50
        if task_type in {"capture", "brief"}:
            score += 5
            reasons["task_type"] = 5
        if source.source_type == "youtube":
            score += 8
            reasons["source_type"] = 8
        elif source.source_type in {"article", "pdf"}:
            score += 4
            reasons["source_type"] = 4
        tags = {normalize_source_tag(tag) for tag in source.tag_snapshot}
        important_tags = tags.intersection({"favorite", "favourite", "pinned", "read", "watch"})
        if important_tags:
            boost = 12
            score += boost
            reasons["important_provider_tags"] = {
                "score": boost,
                "tags": sorted(important_tags),
            }
        provider_values = json.dumps(source.provider_snapshot).lower()
        if any(marker in provider_values for marker in ("favorite", "important", "pinned")):
            score += 10
            reasons["provider_signal"] = 10
        if source.saved_at:
            age_days = max(0, (datetime.now(source.saved_at.tzinfo) - source.saved_at).days)
            if age_days <= 7:
                score += 10
                reasons["recent"] = 10
            elif age_days <= 30:
                score += 5
                reasons["recent"] = 5
        if source.failure_status != "none":
            score -= 20
            reasons["previous_failure"] = -20
        if source.brief_status == "ready" or source.deep_status == "compiled":
            score -= 15
            reasons["already_enriched"] = -15
        if requested_reason:
            reasons["requested_reason"] = requested_reason
        return max(score, 0.0), reasons

    def _prepare_source(self, source: CatalogSource) -> CatalogSource:
        normalized = normalize_url(source.url)
        source.normalized_url = source.normalized_url or normalized
        source.url_hash = source.url_hash or url_hash(source.url)
        if source.canonical_url and not source.canonical_url_hash:
            source.canonical_url_hash = url_hash(source.canonical_url)
        if not source.priority_policy_version:
            source.priority_policy_version = PRIORITY_POLICY_VERSION
        if not source.priority_reasons:
            score, reasons = self.compute_priority(source)
            source.priority_score = score
            source.priority_reasons = reasons
            source.priority_computed_at = datetime.now(source.created_at.tzinfo)
        return source

    def _merge_source(self, existing: CatalogSource, incoming: CatalogSource) -> CatalogSource:
        incoming.uid = existing.uid
        incoming.created_at = existing.created_at
        incoming.url = incoming.url or existing.url
        incoming.normalized_url = incoming.normalized_url or existing.normalized_url
        incoming.url_hash = incoming.url_hash or existing.url_hash
        incoming.canonical_url = incoming.canonical_url or existing.canonical_url
        incoming.canonical_url_hash = incoming.canonical_url_hash or existing.canonical_url_hash
        incoming.content_hash = incoming.content_hash or existing.content_hash
        incoming.source_type = incoming.source_type or existing.source_type
        incoming.title = incoming.title or existing.title
        incoming.description = incoming.description or existing.description
        incoming.author = incoming.author or existing.author
        incoming.site_name = incoming.site_name or existing.site_name
        incoming.language = incoming.language or existing.language
        incoming.published_date = incoming.published_date or existing.published_date
        incoming.saved_at = incoming.saved_at or existing.saved_at
        incoming.metadata_status = _max_status(
            existing.metadata_status,
            incoming.metadata_status,
            ["metadata_only", "captured"],
        )
        incoming.content_status = _max_status(
            existing.content_status,
            incoming.content_status,
            ["not_fetched", "failed", "available"],
        )
        incoming.brief_status = _max_status(
            existing.brief_status,
            incoming.brief_status,
            ["not_started", "failed", "ready"],
        )
        incoming.deep_status = _max_status(
            existing.deep_status,
            incoming.deep_status,
            ["not_started", "failed", "compiled"],
        )
        incoming.output_status = _max_status(
            existing.output_status,
            incoming.output_status,
            ["not_published", "published"],
        )
        incoming.failure_status = incoming.failure_status or existing.failure_status
        incoming.last_failure_reason = incoming.last_failure_reason or existing.last_failure_reason
        incoming.tag_snapshot = incoming.tag_snapshot or existing.tag_snapshot
        incoming.provider_snapshot = incoming.provider_snapshot or existing.provider_snapshot
        return incoming

    def _source_values(
        self, source: CatalogSource, created_at: str, updated_at: str
    ) -> tuple[Any, ...]:
        return (
            source.uid,
            source.url,
            source.normalized_url,
            source.url_hash,
            source.canonical_url,
            source.canonical_url_hash,
            source.content_hash,
            source.source_type,
            source.title,
            source.description,
            source.author,
            source.site_name,
            source.language,
            source.published_date,
            source.saved_at.isoformat() if source.saved_at else None,
            source.metadata_status,
            source.content_status,
            source.brief_status,
            source.deep_status,
            source.output_status,
            source.failure_status,
            source.last_failure_reason,
            json.dumps(source.tag_snapshot, sort_keys=True),
            json.dumps(source.provider_snapshot, sort_keys=True),
            source.priority_score,
            json.dumps(source.priority_reasons, sort_keys=True),
            source.priority_policy_version,
            source.priority_computed_at.isoformat() if source.priority_computed_at else None,
            created_at,
            updated_at,
        )

    def _require_source(self, source_uid: str) -> CatalogSource:
        source = self.get_source(source_uid)
        if source is None:
            raise ValueError(f"Source '{source_uid}' does not exist")
        return source

    def _refresh_tag_snapshot(self, source_uid: str) -> None:
        tags = [tag.normalized_tag for tag in self.tags_for_source(source_uid)]
        self._db.conn.execute(
            "UPDATE sources SET tag_snapshot = ?, updated_at = ? WHERE uid = ?",
            (json.dumps(sorted(set(tags))), iso_now(), source_uid),
        )
        self._db.conn.commit()

    def _refresh_provider_snapshot(self, source_uid: str) -> None:
        refs = self.provider_refs_for_source(source_uid)
        snapshot = {
            ref.provider: {
                "external_id": ref.external_id,
                "title": ref.title,
                "saved_at": ref.saved_at.isoformat() if ref.saved_at else None,
                "metadata": ref.metadata,
            }
            for ref in refs
        }
        self._db.conn.execute(
            "UPDATE sources SET provider_snapshot = ?, updated_at = ? WHERE uid = ?",
            (json.dumps(snapshot, sort_keys=True), iso_now(), source_uid),
        )
        self._db.conn.commit()

    @staticmethod
    def _dt(value: datetime | None) -> str | None:
        return value.isoformat() if value else None

    @staticmethod
    def _row_to_source(row) -> CatalogSource:
        payload = dict(row)
        for field, default in (
            ("tag_snapshot", []),
            ("provider_snapshot", {}),
            ("priority_reasons", {}),
        ):
            payload[field] = _json_value(payload.get(field), default)
        return CatalogSource(**payload)

    @staticmethod
    def _row_to_provider_ref(row) -> SourceProviderRef:
        payload = dict(row)
        payload["metadata"] = _json_value(payload.get("metadata"), {})
        payload["raw_json"] = _json_value(payload.get("raw_json"), {})
        return SourceProviderRef(**payload)

    @staticmethod
    def _row_to_job(row) -> ProcessingJob:
        payload = dict(row)
        payload["priority_reasons"] = _json_value(payload.get("priority_reasons"), {})
        return ProcessingJob(**payload)

    @staticmethod
    def _row_to_processing_attempt(row) -> ProcessingAttempt:
        payload = dict(row)
        payload["success"] = bool(payload.get("success", 0))
        return ProcessingAttempt(**payload)

    @staticmethod
    def _row_to_usage_event(row) -> UsageEvent:
        payload = dict(row)
        payload["metadata"] = _json_value(payload.get("metadata"), {})
        return UsageEvent(**payload)


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


class ReviewSurfaceHistoryRepository:
    def __init__(self, db: Database):
        self._db = db

    def clear_period(self, *, review_type: str, period_key: str) -> None:
        self._db.conn.execute(
            "DELETE FROM review_surface_history WHERE review_type = ? AND period_key = ?",
            (review_type, period_key),
        )
        self._db.conn.commit()

    def replace_period_entries(
        self,
        *,
        review_type: str,
        period_key: str,
        surfaced_at: datetime,
        entries: list[tuple[str, str]],
    ) -> None:
        now = iso_now()
        surfaced_at_value = surfaced_at.isoformat()
        self._db.conn.execute(
            "DELETE FROM review_surface_history WHERE review_type = ? AND period_key = ?",
            (review_type, period_key),
        )
        for source_note_path, reason in entries:
            self._db.conn.execute(
                """INSERT INTO review_surface_history
                   (review_type, period_key, source_note_path, surfaced_at, reason, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    review_type,
                    period_key,
                    source_note_path,
                    surfaced_at_value,
                    reason,
                    now,
                ),
            )
        self._db.conn.commit()

    def list_surfaces_since(
        self,
        *,
        since: datetime,
        review_types: list[str] | None = None,
        exclude_period_key: str | None = None,
    ) -> list[dict[str, str]]:
        query = "SELECT * FROM review_surface_history WHERE surfaced_at >= ?"
        params: list[str] = [since.isoformat()]

        if review_types:
            placeholders = ",".join("?" for _ in review_types)
            query += f" AND review_type IN ({placeholders})"
            params.extend(review_types)

        if exclude_period_key:
            query += " AND period_key != ?"
            params.append(exclude_period_key)

        query += " ORDER BY surfaced_at DESC, id DESC"
        rows = self._db.conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]
