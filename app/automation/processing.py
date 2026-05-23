"""Mode-aware processing pipeline for queued items."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Callable

from app.automation.models import (
    AutomationMode,
    FailureType,
    ItemAttempt,
    ProcessResult,
    QueuedItem,
    QueueItemStatus,
)
from app.automation.queue_store import (
    ItemAttemptRepository,
    QueueRepository,
)
from app.config import Settings, get_settings
from app.events import EventType, publish
from app.storage.sqlite import Database
from app.utils.dates import utcnow
from app.utils.hashing import url_hash as compute_url_hash

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, dict[str, Any]], None]


def _emit_progress(
    progress_callback: ProgressCallback | None,
    stage: str,
    **payload: Any,
) -> None:
    if progress_callback is None:
        return
    try:
        progress_callback(stage, payload)
    except Exception:
        logger.debug("Processing progress callback failed for stage=%s", stage, exc_info=True)


def classify_failure(error: Exception) -> FailureType:
    """Classify an exception into a failure type for retry decisions."""
    error_str = str(error).lower()

    if any(kw in error_str for kw in ("timeout", "timed out", "deadline")):
        return FailureType.TIMEOUT
    if any(kw in error_str for kw in ("rate limit", "429", "too many requests")):
        return FailureType.RATE_LIMIT
    if any(
        kw in error_str
        for kw in ("connection", "network", "dns", "resolve", "refused", "reset")
    ):
        return FailureType.NETWORK
    if any(kw in error_str for kw in ("backend", "unavailable", "no backend")):
        return FailureType.BACKEND_UNAVAILABLE
    if any(kw in error_str for kw in ("unsupported", "not supported", "cannot process")):
        return FailureType.UNSUPPORTED
    if any(
        kw in error_str
        for kw in ("extract", "fetch", "parse", "decode", "scrape")
    ):
        return FailureType.EXTRACTION

    return FailureType.UNKNOWN


def is_retryable(failure_type: FailureType) -> bool:
    """Whether a failure type should be retried."""
    return failure_type in {
        FailureType.NETWORK,
        FailureType.RATE_LIMIT,
        FailureType.EXTRACTION,
        FailureType.BACKEND_UNAVAILABLE,
        FailureType.TIMEOUT,
        FailureType.UNKNOWN,
    }


def compute_backoff(attempt_count: int, base_seconds: int = 60) -> datetime:
    """Compute next retry time using exponential backoff with jitter."""
    delay = base_seconds * (2 ** min(attempt_count, 6))  # Cap at ~64x base
    return utcnow() + timedelta(seconds=delay)


async def process_pending_items(
    mode: str = AutomationMode.SAFE,
    limit: int | None = None,
    retry_failed: bool = False,
    connector_id: str | None = None,
    progress_callback: ProgressCallback | None = None,
) -> list[ProcessResult]:
    """Process pending queued items according to the given mode."""
    settings = get_settings()
    process_limit = limit or settings.automation_process_limit

    db = Database(settings.db_path)
    db.connect()

    try:
        queue_repo = QueueRepository(db)
        attempt_repo = ItemAttemptRepository(db)

        # Reset any stale processing items
        reset_count = queue_repo.reset_stale_processing()
        if reset_count:
            logger.info("Reset %d stale processing items", reset_count)

        items = queue_repo.get_pending(
            limit=process_limit,
            include_retryable=retry_failed,
            connector_id=connector_id,
        )
        _emit_progress(
            progress_callback,
            "process_loaded",
            mode=mode,
            count=len(items),
            connector=connector_id,
        )

        if not items:
            logger.info("No pending items to process")
            return []

        # For balanced/deep modes, check enrichment caps
        enrich_limit = _get_enrich_limit(mode, settings, db, queue_repo)

        logger.info(
            "Processing %d items in %s mode (enrich_limit=%s)",
            len(items),
            mode,
            enrich_limit,
        )

        results: list[ProcessResult] = []
        enriched_count = 0

        total = len(items)
        for index, item in enumerate(items, start=1):
            # Check enrichment budget for balanced/deep modes
            if mode != AutomationMode.SAFE and enrich_limit is not None:
                if enriched_count >= enrich_limit:
                    logger.info(
                        "Enrichment limit reached (%d), remaining items stay queued",
                        enrich_limit,
                    )
                    _emit_progress(
                        progress_callback,
                        "process_budget_reached",
                        mode=mode,
                        limit=enrich_limit,
                        processed=index - 1,
                        total=total,
                    )
                    break

            _emit_progress(
                progress_callback,
                "process_item_start",
                index=index,
                total=total,
                title=item.title or item.url,
                url=item.url,
                mode=mode,
            )
            result = await _process_single_item(
                item=item,
                mode=mode,
                settings=settings,
                queue_repo=queue_repo,
                attempt_repo=attempt_repo,
            )
            results.append(result)

            if result.success:
                _emit_progress(
                    progress_callback,
                    "process_item_done",
                    index=index,
                    total=total,
                    title=item.title or item.url,
                    url=item.url,
                    mode=mode,
                )
            else:
                _emit_progress(
                    progress_callback,
                    "process_item_failed",
                    index=index,
                    total=total,
                    title=item.title or item.url,
                    url=item.url,
                    mode=mode,
                    error=result.error,
                    error_type=result.error_type,
                )

            if result.success and mode != AutomationMode.SAFE:
                enriched_count += 1

        _emit_progress(
            progress_callback,
            "process_done",
            mode=mode,
            succeeded=sum(1 for r in results if r.success),
            failed=sum(1 for r in results if not r.success),
        )
        return results

    finally:
        db.close()


def _get_enrich_limit(
    mode: str,
    settings: Settings,
    db: Database,
    queue_repo: QueueRepository,
) -> int | None:
    """Determine the enrichment limit for this run based on mode and daily caps."""
    if mode == AutomationMode.SAFE:
        return None  # No LLM enrichment in safe mode

    per_run = settings.automation_deep_enrich_limit_per_run
    per_day = settings.automation_deep_enrich_limit_per_day

    if mode == AutomationMode.BALANCED:
        per_run = min(per_run, settings.automation_process_limit)

    # Check daily usage
    used_today = queue_repo.count_completed_today(mode)
    remaining_today = max(0, per_day - used_today)

    return min(per_run, remaining_today)


async def _process_single_item(
    *,
    item: QueuedItem,
    mode: str,
    settings: Settings,
    queue_repo: QueueRepository,
    attempt_repo: ItemAttemptRepository,
) -> ProcessResult:
    """Process a single queued item with error handling."""
    item_id = item.id
    assert item_id is not None

    queue_repo.mark_processing(item_id)

    attempt = ItemAttempt(
        queued_item_id=item_id,
        attempt_number=item.attempt_count + 1,
        mode=mode,
    )

    try:
        if mode == AutomationMode.SAFE:
            result = await _process_safe(item, settings)
        elif mode == AutomationMode.BALANCED:
            result = await _process_enriched(item, settings, mode)
        else:  # deep
            result = await _process_enriched(item, settings, mode)

        # Success
        attempt.success = True
        attempt.finished_at = utcnow()
        attempt.backend_used = result.backend_used
        attempt_repo.insert(attempt)
        processed_source_id = _mark_catalog_success_for_queue_item(
            queue_repo=queue_repo,
            item=item,
            mode=mode,
        )

        queue_repo.update_status(
            item_id,
            QueueItemStatus.COMPLETED,
            mode=mode,
            backend=result.backend_used,
            processed_source_id=processed_source_id,
        )

        result.success = True
        result.queued_item_id = item_id
        result.mode = mode
        return result

    except Exception as exc:
        failure_type = classify_failure(exc)
        retryable = is_retryable(failure_type)

        attempt.success = False
        attempt.error = str(exc)[:500]
        attempt.error_type = failure_type.value
        attempt.finished_at = utcnow()
        attempt_repo.insert(attempt)

        max_attempts = settings.automation_retry_max_attempts
        new_attempt_count = item.attempt_count + 1

        if retryable and new_attempt_count < max_attempts:
            next_retry = compute_backoff(
                new_attempt_count, settings.automation_retry_base_seconds
            )
            queue_repo.update_status(
                item_id,
                QueueItemStatus.RETRYABLE_FAILED,
                error=str(exc)[:500],
                error_type=failure_type.value,
                mode=mode,
                next_attempt_at=next_retry,
            )
            logger.warning(
                "Item %d failed (retryable, attempt %d/%d): %s",
                item_id,
                new_attempt_count,
                max_attempts,
                exc,
            )
        else:
            queue_repo.update_status(
                item_id,
                QueueItemStatus.PERMANENT_FAILED,
                error=str(exc)[:500],
                error_type=failure_type.value,
                mode=mode,
            )
            logger.error(
                "Item %d permanently failed (type=%s, attempts=%d): %s",
                item_id,
                failure_type.value,
                new_attempt_count,
                exc,
            )

        _mark_catalog_failure_for_queue_item(
            queue_repo=queue_repo,
            item=item,
            error=str(exc),
        )
        return ProcessResult(
            queued_item_id=item_id,
            success=False,
            mode=mode,
            error=str(exc)[:500],
            error_type=failure_type.value,
        )


def _mark_catalog_success_for_queue_item(
    *,
    queue_repo: QueueRepository,
    item: QueuedItem,
    mode: str,
) -> int | None:
    from app.models.source_lifecycle import (
        apply_transition,
        brief_published,
        capture_published,
        deep_compiled,
    )
    from app.storage.repositories import SourceCatalogRepository, SourceRepository

    db = queue_repo._db  # noqa: SLF001 - queue and catalog share the same store.
    source_repo = SourceRepository(db)
    processed = source_repo.find_by_url_hash(item.url_hash or compute_url_hash(item.url))
    catalog_repo = SourceCatalogRepository(db)
    catalog_source = catalog_repo.find_by_url_hash(item.url_hash or compute_url_hash(item.url))
    if catalog_source is None:
        return processed.id if processed else None

    if mode == AutomationMode.DEEP:
        transition = deep_compiled(
            content_hash=processed.content_hash if processed else None,
            title=processed.title if processed and processed.title else None,
            source_type=processed.source_type if processed and processed.source_type else None,
        )
    elif mode == AutomationMode.BALANCED:
        transition = brief_published(content_hash=processed.content_hash if processed else None)
    else:
        transition = capture_published(
            content_hash=processed.content_hash if processed else None,
            title=processed.title if processed and processed.title else None,
            source_type=processed.source_type if processed and processed.source_type else None,
        )
    apply_transition(catalog_repo, catalog_source.uid, transition)
    return processed.id if processed else None


def _mark_catalog_failure_for_queue_item(
    *,
    queue_repo: QueueRepository,
    item: QueuedItem,
    error: str,
) -> None:
    from app.models.source_lifecycle import apply_transition, partial_failure
    from app.storage.repositories import SourceCatalogRepository

    db = queue_repo._db  # noqa: SLF001 - queue and catalog share the same store.
    catalog_repo = SourceCatalogRepository(db)
    catalog_source = catalog_repo.find_by_url_hash(item.url_hash or compute_url_hash(item.url))
    if catalog_source is None:
        return
    apply_transition(catalog_repo, catalog_source.uid, partial_failure(error))


async def _process_safe(item: QueuedItem, settings: Settings) -> ProcessResult:
    """Safe mode: fetch, archive, minimal note, no expensive LLM enrichment."""
    from app.artifacts import build_artifact_bundle
    from app.connectors.classifier import classify_url
    from app.connectors.fetchers import fetch_content
    from app.models.source import SourceItem
    from app.sinks.registry import build_default_sink
    from app.storage.repositories import SourceRepository
    from app.storage.sqlite import Database
    from app.utils.hashing import url_hash as compute_url_hash
    from app.utils.slugify import slugify

    source_type = classify_url(item.url)
    tags = []
    try:
        tags = json.loads(item.tags) if item.tags else []
    except (json.JSONDecodeError, TypeError):
        pass

    source_item = SourceItem(
        url=item.url,
        title=item.title,
        source_type=source_type,
        tags=tags,
        saved_at=item.saved_at,
        inbox_provider=item.connector_id,
        external_id=item.external_id,
        provider_metadata=item.provider_metadata,
    )

    # Fetch content (this is safe — no LLM cost)
    content = await fetch_content(source_item)
    slug = slugify(content.source.title or item.url)

    # Write a minimal source note using text-only fallback analysis
    from app.compiler.ingest_graph import (
        _bullet_list,
        _clip_paragraphs,
        _extract_key_points,
        _fallback_analysis,
        _fallback_outline,
        _fallback_quotes,
        _fallback_reading_note,
    )

    text = content.cleaned_text or content.raw_text
    excerpt = _clip_paragraphs(text, max_paragraphs=4, max_chars=1500) if text else ""
    key_points = _extract_key_points(text) if text else []

    analysis = _fallback_analysis(
        source_type=content.source.source_type.value,
        summary=(
            f"Source captured in safe mode (no LLM enrichment). "
            f"Title: {content.source.title or item.url}"
        ),
        five_minute_read=excerpt or "Content captured; see raw archive.",
        detailed_reading_note=(
            _fallback_reading_note(content, text)
            if text
            else "No text extracted."
        ),
        key_ideas=_bullet_list(key_points[:5], "- See raw archive for details."),
        detailed_outline=(
            _fallback_outline(text)
            if text
            else "## Capture Status\n- Safe mode capture"
        ),
        important_examples="- Review the raw archive for concrete examples.",
        actionable_takeaways=(
            "- Re-run in balanced or deep mode for richer AI analysis.\n"
            "- The raw archive preserves the source text."
        ),
        notable_quotes=_fallback_quotes(text) if text else "- None captured.",
        best_for="- Quick reference and safe archival.",
        consume_recommendation="Open the original source for full context.",
        why_it_matters="Captured for the knowledge vault; pending deeper enrichment.",
        open_questions="- Does this source deserve deeper AI analysis?",
    )

    artifact_bundle = build_artifact_bundle(
        content=content,
        slug=slug,
        analysis=analysis,
    )
    sink = build_default_sink(settings)
    updates = sink.publish(content=content, bundle=artifact_bundle)
    raw_update = next(update for update in updates if update.note_type == "raw_capture")
    source_update = next(update for update in updates if update.note_type == "source")

    # Persist in processed_sources
    from app.models.db import ProcessedSource

    db = Database(settings.db_path)
    db.connect()
    try:
        source_repo = SourceRepository(db)
        source_repo.upsert(
            ProcessedSource(
                url=content.source.url,
                url_hash=content.url_hash or compute_url_hash(content.source.url),
                content_hash=content.content_hash or "",
                source_type=content.source.source_type.value,
                title=content.source.title or item.url,
                source_note_path=source_update.path,
                raw_capture_path=raw_update.path,
                provider=item.connector_id,
                external_id=item.external_id,
                provider_metadata=item.provider_metadata,
                status="completed",
            )
        )
    finally:
        db.close()

    publish(
        EventType.SOURCE_INGESTED,
        source_url=content.source.url,
        source_title=content.source.title or item.url,
        source_type=content.source.source_type.value,
        source_note_path=source_update.path,
        raw_capture_path=raw_update.path,
        deduplicated=False,
    )

    return ProcessResult(
        queued_item_id=item.id or 0,
        success=True,
        mode=AutomationMode.SAFE,
        backend_used="none",
        source_note_path=source_update.path,
        raw_capture_path=raw_update.path,
        changed_paths=[update.path for update in updates],
    )


async def _process_enriched(
    item: QueuedItem,
    settings: Settings,
    mode: str,
) -> ProcessResult:
    """Balanced/Deep mode: full ingest graph with LLM enrichment."""
    from app.compiler.ingest_graph import get_ingest_graph
    from app.connectors.classifier import classify_url
    from app.models.source import SourceItem

    source_type = classify_url(item.url)
    tags = []
    try:
        tags = json.loads(item.tags) if item.tags else []
    except (json.JSONDecodeError, TypeError):
        pass

    source_item = SourceItem(
        url=item.url,
        title=item.title,
        source_type=source_type,
        tags=tags,
        saved_at=item.saved_at,
        inbox_provider=item.connector_id,
        external_id=item.external_id,
        provider_metadata=item.provider_metadata,
    )

    graph = get_ingest_graph()
    final_state = await graph.ainvoke({"item": source_item, "force_reingest": True})

    result = final_state.get("result")
    if not result:
        raise RuntimeError("Ingest graph did not produce a result")

    if result.errors:
        raise RuntimeError("; ".join(result.errors))

    return ProcessResult(
        queued_item_id=item.id or 0,
        success=True,
        mode=mode,
        backend_used="ingest_graph",
        source_note_path=result.source_note_path,
        raw_capture_path=result.raw_capture_path,
        changed_paths=[update.path for update in result.vault_updates],
    )
