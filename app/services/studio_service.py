from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.automation.models import QueuedItem
from app.automation.processing import _process_single_item, classify_failure
from app.automation.queue_store import ItemAttemptRepository, QueueRepository
from app.config import Settings, get_settings
from app.connectors.classifier import classify_url
from app.models.db import CatalogSource, ProcessingAttempt, ProcessingJob, SourceProviderRef
from app.models.studio import (
    StudioAction,
    StudioKnowledgeDetailResponse,
    StudioKnowledgeListResponse,
    StudioKnowledgeNote,
    StudioProcessingJobResponse,
    StudioProviderRefResponse,
    StudioSearchHit,
    StudioSearchResponse,
    StudioSourceDetail,
    StudioSourceReaderResponse,
    StudioSourceSummary,
    StudioStatsResponse,
    StudioTagResponse,
)
from app.read_model.store import ReadModelStore
from app.services.brief_service import (
    BriefCompilationResult,
    compile_pending_source_briefs,
    compile_source_brief,
)
from app.services.readwise_import_service import ReadwiseImportResult, import_readwise_sources
from app.storage.repositories import SourceCatalogRepository, SourceRepository
from app.storage.sqlite import Database
from app.utils.dates import utcnow
from app.utils.hashing import url_hash
from app.utils.http import assert_safe_http_url
from app.utils.markdown import parse_frontmatter
from app.vault.parser import scan_vault

ACTION_MODE: dict[str, str] = {
    "capture": "safe",
    "brief": "balanced",
    "deep_compile": "deep",
    "refresh": "safe",
}

KNOWLEDGE_NOTE_TYPES = {"topic", "entity", "concept", "synthesis"}


def list_studio_sources(
    db: Database,
    *,
    query: str = "",
    limit: int = 50,
    metadata_only: bool = False,
    source_type: str = "",
    display_state: str = "",
    provider: str = "",
    tag: str = "",
) -> list[StudioSourceSummary]:
    repo = SourceCatalogRepository(db)
    sources = repo.list_sources(
        limit=limit,
        query=query,
        metadata_only=metadata_only,
        source_type=source_type,
        display_state=display_state,
        provider=provider,
        tag=tag,
    )
    return [StudioSourceSummary.from_source(source) for source in sources]


def get_studio_source_detail(db: Database, source_uid: str) -> StudioSourceDetail | None:
    repo = SourceCatalogRepository(db)
    source = repo.get_source(source_uid)
    if source is None:
        return None
    processed = SourceRepository(db).find_by_url_hash(source.url_hash or url_hash(source.url))
    payload = StudioSourceSummary.from_source(source).model_dump()
    payload.update(
        {
            "author": source.author,
            "language": source.language,
            "published_date": source.published_date,
            "canonical_url": source.canonical_url,
            "content_hash": source.content_hash,
            "source_note_path": processed.source_note_path if processed else "",
            "raw_capture_path": processed.raw_capture_path if processed else "",
            "provider_refs": [
                StudioProviderRefResponse.from_ref(ref)
                for ref in repo.provider_refs_for_source(source_uid)
            ],
            "tags": [
                StudioTagResponse.from_tag(tag)
                for tag in repo.tags_for_source(source_uid)
            ],
            "latest_jobs": [
                _job_to_response(repo, job, source=source)
                for job in repo.latest_jobs_for_source(source_uid, limit=10)
            ],
        }
    )
    return StudioSourceDetail(**payload)


def _job_to_response(
    repo: SourceCatalogRepository,
    job: ProcessingJob,
    *,
    source: CatalogSource | None = None,
) -> StudioProcessingJobResponse:
    if source is None or source.uid != job.source_uid:
        source = repo.get_source(job.source_uid)
    attempt_count = repo.processing_attempt_count(job.job_uid)
    return StudioProcessingJobResponse.from_job(
        job,
        source_title=source.title if source else "",
        source_url=source.url if source else "",
        source_type=source.source_type if source else "",
        attempt_count=attempt_count,
    )


def list_studio_jobs(
    db: Database,
    *,
    limit: int = 50,
    status: str = "",
) -> list[StudioProcessingJobResponse]:
    repo = SourceCatalogRepository(db)
    jobs = repo.list_processing_jobs(limit=limit, status=status)
    return [_job_to_response(repo, job) for job in jobs]


def get_studio_source_reader(
    db: Database,
    source_uid: str,
    *,
    vault_path: Path,
) -> StudioSourceReaderResponse | None:
    repo = SourceCatalogRepository(db)
    source = repo.get_source(source_uid)
    if source is None:
        return None
    processed = SourceRepository(db).find_by_url_hash(source.url_hash or url_hash(source.url))
    source_note_path = processed.source_note_path if processed else ""
    raw_capture_path = processed.raw_capture_path if processed else ""
    source_markdown = _read_vault_markdown(vault_path, source_note_path)
    raw_markdown = _read_vault_markdown(vault_path, raw_capture_path)
    source_meta, source_body = _safe_parse_frontmatter(source_markdown)
    raw_meta, raw_body = _safe_parse_frontmatter(raw_markdown)
    return StudioSourceReaderResponse(
        source_uid=source.uid,
        url=source.url,
        title=source.title,
        source_type=source.source_type,
        description=source.description,
        author=source.author,
        site_name=source.site_name,
        published_date=source.published_date,
        saved_at=source.saved_at,
        source_note_path=source_note_path,
        raw_capture_path=raw_capture_path,
        source_markdown=source_markdown,
        raw_markdown=raw_markdown,
        has_source_note=bool(source_markdown),
        has_raw_capture=bool(raw_markdown),
        source_frontmatter=_jsonable_meta(source_meta),
        source_body=source_body,
        raw_frontmatter=_jsonable_meta(raw_meta),
        raw_body=raw_body,
    )


def _read_vault_markdown(vault_path: Path, relative_path: str) -> str:
    if not relative_path:
        return ""
    root = vault_path.expanduser().resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return ""
    if not candidate.is_file():
        return ""
    return candidate.read_text(encoding="utf-8")


def _safe_parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text:
        return {}, ""
    try:
        meta, body = parse_frontmatter(text)
    except Exception:
        return {}, text
    return dict(meta or {}), body


def _jsonable_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """Convert markdown frontmatter values to JSON-serializable shapes."""
    result: dict[str, Any] = {}
    for key, value in meta.items():
        if isinstance(value, datetime):
            result[key] = value.isoformat()
        elif hasattr(value, "isoformat"):
            try:
                result[key] = value.isoformat()  # type: ignore[no-untyped-call]
            except Exception:
                result[key] = str(value)
        elif isinstance(value, (list, tuple)):
            result[key] = [
                v.isoformat() if isinstance(v, datetime) else v for v in value
            ]
        else:
            result[key] = value
    return result


def manual_add_url(
    db: Database,
    *,
    url: str,
    title: str = "",
    tags: list[str] | None = None,
    enqueue_action: StudioAction | None = None,
) -> tuple[StudioSourceDetail, ProcessingJob | None]:
    assert_safe_http_url(url)
    repo = SourceCatalogRepository(db)
    source_type = classify_url(url).value
    source = repo.upsert_source(
        CatalogSource(
            url=url,
            title=title,
            source_type=source_type,
            metadata_status="metadata_only",
            content_status="not_fetched",
            provider_snapshot={"manual": {"added_at": utcnow().isoformat()}},
        )
    )
    repo.attach_provider_ref(
        SourceProviderRef(
            source_uid=source.uid,
            provider="manual",
            external_id="",
            external_url=url,
            saved_at=utcnow(),
            title=title,
            metadata={"source": "studio_manual_add"},
            raw_json={"url": url, "title": title, "tags": tags or []},
        )
    )
    if tags:
        repo.sync_tags(source.uid, tags, origin="user")

    job = None
    if enqueue_action is not None:
        job = enqueue_source_action(
            db,
            source_uid=source.uid,
            action=enqueue_action,
            requested_by="studio",
            requested_reason="manual URL add",
        )
    detail = get_studio_source_detail(db, source.uid)
    assert detail is not None
    return detail, job


def enqueue_source_action(
    db: Database,
    *,
    source_uid: str,
    action: StudioAction,
    requested_by: str = "studio",
    requested_reason: str = "",
) -> ProcessingJob:
    if action not in ACTION_MODE:
        raise ValueError(f"Unsupported Studio action: {action}")
    repo = SourceCatalogRepository(db)
    return repo.enqueue_processing_job(
        source_uid=source_uid,
        task_type=action,
        mode=ACTION_MODE[action],
        requested_by=requested_by,
        requested_reason=requested_reason,
    )


async def process_source_jobs_once(
    *,
    settings: Settings | None = None,
    limit: int = 5,
) -> list[ProcessingJob]:
    settings = settings or get_settings()
    db = Database(settings.db_path)
    db.connect()
    try:
        catalog_repo = SourceCatalogRepository(db)
        queue_repo = QueueRepository(db)
        attempt_repo = ItemAttemptRepository(db)
        jobs = catalog_repo.next_processing_jobs(limit=limit)
        completed: list[ProcessingJob] = []
        for job in jobs:
            completed.append(
                await _process_one_source_job(
                    job=job,
                    settings=settings,
                    catalog_repo=catalog_repo,
                    queue_repo=queue_repo,
                    attempt_repo=attempt_repo,
                )
            )
        return completed
    finally:
        db.close()


async def sync_readwise_for_studio(
    *,
    limit: int = 100,
    force: bool = False,
    auto_brief_limit: int | None = None,
) -> ReadwiseImportResult:
    return await import_readwise_sources(
        limit=limit,
        force=force,
        auto_brief=auto_brief_limit is not None,
        auto_brief_limit=auto_brief_limit,
    )


async def compile_pending_briefs_for_studio(
    *,
    limit: int = 5,
    force: bool = False,
) -> BriefCompilationResult:
    return await compile_pending_source_briefs(limit=limit, force=force)


async def compile_source_brief_for_studio(
    *,
    source_uid: str,
    force: bool = False,
) -> BriefCompilationResult:
    return await compile_source_brief(source_uid, force=force)


async def _process_one_source_job(
    *,
    job: ProcessingJob,
    settings: Settings,
    catalog_repo: SourceCatalogRepository,
    queue_repo: QueueRepository,
    attempt_repo: ItemAttemptRepository,
) -> ProcessingJob:
    source = catalog_repo.get_source(job.source_uid)
    if source is None:
        return catalog_repo.mark_processing_job_failed(
            job.job_uid,
            error=f"Source '{job.source_uid}' does not exist",
        )

    catalog_repo.mark_processing_job_running(job.job_uid)
    queued_item_id = job.queued_item_id or _ensure_queue_item_for_job(
        job=job,
        source=source,
        catalog_repo=catalog_repo,
        queue_repo=queue_repo,
    )
    queued_item = queue_repo.find_by_url_hash(source.url_hash)
    if queued_item is None or queued_item.id != queued_item_id:
        queued_item = queue_repo.get(queued_item_id)
    if queued_item is None:
        return catalog_repo.mark_processing_job_failed(
            job.job_uid,
            error=f"Queued item '{queued_item_id}' does not exist",
        )

    attempt_number = catalog_repo.processing_attempt_count(job.job_uid) + 1
    started_at = utcnow()
    try:
        result = await _process_single_item(
            item=queued_item,
            mode=job.mode,
            settings=settings,
            queue_repo=queue_repo,
            attempt_repo=attempt_repo,
        )
        finished_at = utcnow()
        processed_source_id = _processed_source_id_for_url(settings, source.url)
        if result.success:
            catalog_repo.record_processing_attempt(
                ProcessingAttempt(
                    job_uid=job.job_uid,
                    attempt_number=attempt_number,
                    backend_used=result.backend_used,
                    started_at=started_at,
                    finished_at=finished_at,
                    success=True,
                )
            )
            _mark_source_success(
                catalog_repo,
                source_uid=source.uid,
                job=job,
                processed_source_id=processed_source_id,
            )
            return catalog_repo.mark_processing_job_completed(
                job.job_uid,
                processed_source_id=processed_source_id,
                queued_item_id=queued_item_id,
            )

        catalog_repo.record_processing_attempt(
            ProcessingAttempt(
                job_uid=job.job_uid,
                attempt_number=attempt_number,
                backend_used=result.backend_used,
                started_at=started_at,
                finished_at=finished_at,
                success=False,
                error=result.error,
                error_type=result.error_type,
            )
        )
        _mark_source_failure(catalog_repo, source.uid, result.error)
        return catalog_repo.mark_processing_job_failed(
            job.job_uid,
            error=result.error,
            queued_item_id=queued_item_id,
        )
    except Exception as exc:
        failure_type = classify_failure(exc)
        catalog_repo.record_processing_attempt(
            ProcessingAttempt(
                job_uid=job.job_uid,
                attempt_number=attempt_number,
                started_at=started_at,
                finished_at=utcnow(),
                success=False,
                error=str(exc)[:500],
                error_type=failure_type.value,
            )
        )
        _mark_source_failure(catalog_repo, source.uid, str(exc))
        return catalog_repo.mark_processing_job_failed(
            job.job_uid,
            error=str(exc),
            queued_item_id=queued_item_id,
        )


def _ensure_queue_item_for_job(
    *,
    job: ProcessingJob,
    source: CatalogSource,
    catalog_repo: SourceCatalogRepository,
    queue_repo: QueueRepository,
) -> int:
    existing = queue_repo.find_by_url_hash(source.url_hash)
    if existing and existing.status in {"discovered", "retryable_failed"}:
        assert existing.id is not None
        catalog_repo.set_job_queued_item(job.job_uid, existing.id)
        return existing.id

    item_id = queue_repo.insert(
        QueuedItem(
            connector_id="studio",
            external_id=job.job_uid,
            url=source.url,
            url_hash=source.url_hash or url_hash(source.url),
            title=source.title,
            source_type=source.source_type,
            tags=json.dumps(source.tag_snapshot),
            saved_at=source.saved_at or datetime.now(timezone.utc),
            status="discovered",
            provider_metadata={"source_uid": source.uid, "task_type": job.task_type},
        )
    )
    catalog_repo.set_job_queued_item(job.job_uid, item_id)
    return item_id


def _processed_source_id_for_url(settings: Settings, url: str) -> int | None:
    db = Database(settings.db_path)
    db.connect()
    try:
        source = SourceRepository(db).find_by_url_hash(url_hash(url))
        return source.id if source else None
    finally:
        db.close()


def _mark_source_success(
    catalog_repo: SourceCatalogRepository,
    *,
    source_uid: str,
    job: ProcessingJob,
    processed_source_id: int | None,
) -> None:
    processed = None
    if processed_source_id is not None:
        processed = SourceRepository(catalog_repo._db).find_by_id(processed_source_id)  # noqa: SLF001

    common = {
        "metadata_status": "captured",
        "content_status": "available",
        "output_status": "published",
        "failure_status": "none",
        "last_failure_reason": "",
        "content_hash": processed.content_hash if processed else None,
        "title": processed.title if processed else None,
        "source_type": processed.source_type if processed else None,
    }
    if job.task_type == "deep_compile":
        catalog_repo.update_lifecycle(
            source_uid,
            brief_status="ready",
            deep_status="compiled",
            **common,
        )
    elif job.task_type == "brief":
        catalog_repo.update_lifecycle(source_uid, brief_status="ready", **common)
    else:
        catalog_repo.update_lifecycle(source_uid, **common)


def _mark_source_failure(
    catalog_repo: SourceCatalogRepository,
    source_uid: str,
    error: str,
) -> None:
    catalog_repo.update_lifecycle(
        source_uid,
        failure_status="partial",
        last_failure_reason=error[:500],
    )


def list_knowledge_notes(
    *,
    note_type: str,
    vault_path: Path,
    limit: int = 200,
) -> StudioKnowledgeListResponse:
    if note_type not in KNOWLEDGE_NOTE_TYPES:
        raise ValueError(f"Unsupported knowledge note type: {note_type}")
    notes: list[StudioKnowledgeNote] = []
    try:
        store = ReadModelStore(vault_path)
        store.ensure_populated()
        for note in store.list_notes(note_type=note_type, limit=limit):
            notes.append(
                StudioKnowledgeNote(
                    note_path=note.note_path,
                    note_type=note.note_type,
                    title=note.title,
                    snippet=_truncate(note.body, 220),
                    tags=list(note.tags),
                    topics=list(note.topics),
                    entities=list(note.entities),
                    concepts=list(note.concepts),
                    source_url=note.source_url,
                    source_type=note.source_type,
                )
            )
    except Exception:
        # Read model not yet populated or unavailable: fall back to filesystem scan.
        notes = _scan_vault_knowledge(vault_path, note_type, limit=limit)

    notes.sort(key=lambda item: item.title.lower())
    return StudioKnowledgeListResponse(note_type=note_type, notes=notes)


def get_knowledge_detail(
    *,
    note_path: str,
    vault_path: Path,
) -> StudioKnowledgeDetailResponse | None:
    safe = _resolve_within(vault_path, note_path)
    if safe is None or not safe.is_file():
        return None
    text = safe.read_text(encoding="utf-8")
    meta, body = _safe_parse_frontmatter(text)
    note_type = _infer_note_type_from_path(note_path) or str(meta.get("type", "")) or "unknown"
    title = str(meta.get("title", "")) or safe.stem
    return StudioKnowledgeDetailResponse(
        note_path=note_path,
        note_type=note_type,
        title=title,
        body=body,
        frontmatter=_jsonable_meta(meta),
        tags=_string_list(meta.get("tags")),
        topics=_string_list(meta.get("topics")),
        entities=_string_list(meta.get("entities")),
        concepts=_string_list(meta.get("concepts")),
        source_url=str(meta.get("source_url", "") or ""),
        source_type=str(meta.get("source_type", "") or ""),
    )


def _scan_vault_knowledge(
    vault_path: Path,
    note_type: str,
    *,
    limit: int,
) -> list[StudioKnowledgeNote]:
    notes: list[StudioKnowledgeNote] = []
    try:
        for note in scan_vault(vault_path):
            if note.note_type != note_type:
                continue
            notes.append(
                StudioKnowledgeNote(
                    note_path=note.rel_path,
                    note_type=note.note_type,
                    title=note.title,
                    snippet=_truncate(note.body, 220),
                    tags=_string_list(note.meta.get("tags")),
                    topics=_string_list(note.meta.get("topics")),
                    entities=_string_list(note.meta.get("entities")),
                    concepts=_string_list(note.meta.get("concepts")),
                    source_url=str(note.meta.get("source_url", "") or ""),
                    source_type=str(note.meta.get("source_type", "") or ""),
                )
            )
            if len(notes) >= limit:
                break
    except Exception:
        return []
    return notes


def _resolve_within(vault_path: Path, relative_path: str) -> Path | None:
    if not relative_path:
        return None
    root = vault_path.expanduser().resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _infer_note_type_from_path(rel_path: str) -> str:
    parts = rel_path.replace("\\", "/").split("/")
    for marker in ("topics", "entities", "concepts", "synthesis", "sources"):
        if marker in parts:
            return marker.rstrip("s")
    return ""


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _truncate(text: str, max_chars: int) -> str:
    collapsed = re.sub(r"\s+", " ", text or "").strip()
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 1].rstrip() + "\u2026"


def studio_search(
    db: Database,
    *,
    query: str,
    vault_path: Path,
    limit: int = 25,
    source_type: str = "",
    display_state: str = "",
) -> StudioSearchResponse:
    repo = SourceCatalogRepository(db)
    catalog_sources = repo.list_sources(
        limit=limit,
        query=query,
        source_type=source_type,
        display_state=display_state,
    )
    hits: list[StudioSearchHit] = []
    seen_urls: set[str] = set()
    for source in catalog_sources:
        seen_urls.add(source.url)
        provenance = ["catalog"]
        if source.metadata_status == "metadata_only":
            provenance.append("metadata_only")
        hits.append(
            StudioSearchHit(
                kind="source",
                title=source.title or source.url,
                url=source.url,
                snippet=_truncate(source.description, 220),
                source_uid=source.uid,
                source_type=source.source_type,
                display_state=_derive_display_state_value(source),
                score=float(source.priority_score or 0.0),
                provenance=provenance,
            )
        )

    if query.strip():
        try:
            store = ReadModelStore(vault_path)
            store.ensure_populated()
            structured = store.search_structured(
                query, limit=limit, note_types={"topic", "entity", "concept", "synthesis"}
            )
            for item in structured:
                hits.append(
                    StudioSearchHit(
                        kind="note",
                        title=str(item.get("title", "")),
                        snippet=str(item.get("snippet", "")),
                        note_path=str(item.get("note_path", "")),
                        note_type=str(item.get("note_type", "")),
                        score=float(item.get("score") or 0.0),
                        provenance=["read_model"],
                    )
                )
            lexical = store.search_lexical(query, limit=limit)
            for item in lexical:
                note_path = str(item.get("note_path", ""))
                if any(hit.note_path == note_path for hit in hits if hit.kind == "note"):
                    continue
                hits.append(
                    StudioSearchHit(
                        kind="note",
                        title=str(item.get("title", "")),
                        snippet=str(item.get("snippet", "")),
                        note_path=note_path,
                        note_type=str(item.get("note_type", "")),
                        score=-float(item.get("score") or 0.0),
                        provenance=["vault"],
                    )
                )
        except Exception:
            pass

    hits.sort(key=lambda h: (-h.score, h.title.lower()))
    return StudioSearchResponse(query=query, hits=hits[:limit])


def _derive_display_state_value(source: CatalogSource) -> str:
    from app.models.studio import derive_display_state

    return derive_display_state(source)


def get_studio_stats(
    db: Database,
    *,
    vault_path: Path,
) -> StudioStatsResponse:
    catalog_repo = SourceCatalogRepository(db)
    queue_repo = QueueRepository(db)
    sources = catalog_repo.list_sources(limit=10_000)
    by_state = {
        "metadata_only": 0,
        "captured": 0,
        "brief_ready": 0,
        "deep_compiled": 0,
        "failed": 0,
    }
    by_source_type: dict[str, int] = {}
    for source in sources:
        state = _derive_display_state_value(source)
        if state == "metadata_only":
            by_state["metadata_only"] += 1
        elif state in {"content_available"}:
            by_state["captured"] += 1
        elif state == "brief_ready":
            by_state["brief_ready"] += 1
        elif state == "deep_compiled":
            by_state["deep_compiled"] += 1
        elif state in {"failed", "failed_partial"}:
            by_state["failed"] += 1
        if source.source_type:
            by_source_type[source.source_type] = by_source_type.get(source.source_type, 0) + 1

    job_counts: dict[str, int] = {}
    rows = db.conn.execute(
        "SELECT status, COUNT(*) AS c FROM processing_jobs GROUP BY status"
    ).fetchall()
    for row in rows:
        job_counts[row["status"]] = int(row["c"])

    note_counts: dict[str, int] = {}
    try:
        store = ReadModelStore(vault_path)
        store.ensure_populated()
        rows = store.list_notes(limit=10_000)
        for note in rows:
            note_counts[note.note_type] = note_counts.get(note.note_type, 0) + 1
    except Exception:
        try:
            for note in scan_vault(vault_path):
                note_counts[note.note_type] = note_counts.get(note.note_type, 0) + 1
        except Exception:
            note_counts = {}

    return StudioStatsResponse(
        total_sources=len(sources),
        metadata_only_sources=by_state["metadata_only"],
        captured_sources=by_state["captured"],
        brief_ready_sources=by_state["brief_ready"],
        deep_compiled_sources=by_state["deep_compiled"],
        failed_sources=by_state["failed"],
        queue_jobs=job_counts,
        queue_items=queue_repo.count_by_status(),
        by_source_type=by_source_type,
        note_counts=note_counts,
    )


def default_snapshot_path(settings: Settings, *, timestamp: datetime | None = None) -> Path:
    stamp = (timestamp or utcnow()).strftime("%Y%m%dT%H%M%SZ")
    return (
        Path(settings.vault_path)
        / ".system"
        / "exports"
        / "source_catalog"
        / f"source_catalog_{stamp}.jsonl"
    )
