"""Readwise import flow for extracted provider content."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.config import get_settings
from app.connectors.registry import get_inbox_connector
from app.models.db import CatalogSource, SourceProviderRef, SyncCursor
from app.models.source import ProviderContentMode, SourceContent, SourceItem
from app.services.brief_service import BriefCompilationResult, compile_pending_source_briefs
from app.sinks.markdown_vault import MarkdownVaultSink
from app.storage.evidence import evidence_storage_policy_from_settings
from app.storage.repositories import (
    SourceCatalogRepository,
    SyncCursorRepository,
)
from app.storage.sqlite import Database
from app.utils.hashing import content_hash as compute_content_hash
from app.utils.hashing import url_hash as compute_url_hash
from app.utils.slugify import slugify

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[str, dict[str, Any]], None]


@dataclass(frozen=True)
class ReadwiseImportedSource:
    source_uid: str
    url: str
    raw_capture_path: str


@dataclass(frozen=True)
class ReadwiseImportResult:
    imported: list[ReadwiseImportedSource] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    auto_brief_result: BriefCompilationResult | None = None

    @property
    def imported_count(self) -> int:
        return len(self.imported)

    @property
    def failed_count(self) -> int:
        return len(self.failures)


async def import_readwise_sources(
    *,
    limit: int = 100,
    force: bool = False,
    auto_brief: bool = False,
    auto_brief_limit: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> ReadwiseImportResult:
    """Import Readwise extracted content without running LLM-backed briefing."""
    settings = get_settings()
    connector = get_inbox_connector("readwise", settings)

    db = Database(settings.db_path)
    db.connect()
    catalog_repo = SourceCatalogRepository(db)
    cursor_repo = SyncCursorRepository(db)
    last_cursor = cursor_repo.get(connector.connector_id)
    since = (
        datetime(2020, 1, 1, tzinfo=timezone.utc)
        if force or last_cursor is None
        else last_cursor.last_sync_at
    )

    sink = MarkdownVaultSink(
        Path(settings.vault_path),
        storage_policy=evidence_storage_policy_from_settings(settings),
    )
    sink.ensure_structure()

    imported: list[ReadwiseImportedSource] = []
    failures: list[str] = []

    try:
        _emit_progress(progress_callback, "readwise_import_start", limit=limit)
        items = connector.fetch_since(since, limit=limit)
        for item in items:
            try:
                imported.append(
                    _import_item(
                        item,
                        catalog_repo=catalog_repo,
                        sink=sink,
                        force=force,
                    )
                )
            except Exception as exc:
                logger.warning("Readwise import failed for %s: %s", item.url, exc)
                _record_failure(item, catalog_repo=catalog_repo, error=str(exc))
                failures.append(f"{item.url}: {exc}")

        cursor_repo.upsert(SyncCursor(connector=connector.connector_id))
        _emit_progress(
            progress_callback,
            "readwise_import_done",
            imported_count=len(imported),
            failed_count=len(failures),
        )
        auto_brief_result = None
        resolved_auto_brief_limit = 5 if auto_brief_limit is None else auto_brief_limit
        should_auto_brief = auto_brief or auto_brief_limit is not None
        if should_auto_brief and resolved_auto_brief_limit > 0 and imported:
            _emit_progress(
                progress_callback,
                "readwise_auto_brief_start",
                limit=resolved_auto_brief_limit,
            )
            auto_brief_result = await compile_pending_source_briefs(
                limit=resolved_auto_brief_limit
            )
            _emit_progress(
                progress_callback,
                "readwise_auto_brief_done",
                compiled_count=auto_brief_result.compiled_count,
                failed_count=auto_brief_result.failed_count,
            )
        return ReadwiseImportResult(
            imported=imported,
            failures=failures,
            auto_brief_result=auto_brief_result,
        )
    finally:
        db.close()


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
        logger.debug("Readwise progress callback failed for stage=%s", stage, exc_info=True)


def _import_item(
    item: SourceItem,
    *,
    catalog_repo: SourceCatalogRepository,
    sink: MarkdownVaultSink,
    force: bool,
) -> ReadwiseImportedSource:
    content = _source_content_from_pre_extracted(item)
    slug = slugify(item.title or item.url) or compute_url_hash(item.url)
    raw_update = sink.write_raw_capture(content, slug)
    existing = catalog_repo.find_by_url_hash(compute_url_hash(item.url))
    if existing and existing.content_status == "available" and not force:
        catalog = existing
    else:
        catalog = catalog_repo.upsert_source(
            CatalogSource(
                url=item.url,
                url_hash=content.url_hash,
                canonical_url=content.canonical_url,
                content_hash=content.content_hash,
                source_type=item.source_type.value,
                title=item.title or item.url,
                author=content.author,
                published_date=content.published_date,
                saved_at=item.saved_at,
                metadata_status="captured",
                content_status="available",
                brief_status="not_started",
                output_status="not_published",
                failure_status="none",
                last_failure_reason="",
            )
        )

    catalog_repo.attach_provider_ref(
        SourceProviderRef(
            source_uid=catalog.uid,
            provider=item.inbox_provider or "readwise",
            external_id=item.external_id,
            external_url=item.url,
            saved_at=item.saved_at,
            title=item.title or item.url,
            metadata=item.provider_metadata,
            raw_json=_provider_raw_json(item),
        )
    )
    if item.tags:
        catalog_repo.sync_tags(catalog.uid, item.tags, origin="provider")

    return ReadwiseImportedSource(
        source_uid=catalog.uid,
        url=item.url,
        raw_capture_path=raw_update.path,
    )


def _source_content_from_pre_extracted(item: SourceItem) -> SourceContent:
    if item.provider_content_mode != ProviderContentMode.EXTRACTED_CONTENT:
        raise ValueError("Readwise import requires extracted provider content")
    if item.pre_extracted_content is None:
        raise ValueError("Readwise item did not include pre-extracted content")

    extracted = item.pre_extracted_content
    body = extracted.archived_markdown or extracted.cleaned_text or extracted.raw_text
    content_hash = extracted.content_hash or compute_content_hash(body)
    return SourceContent(
        source=item,
        raw_text=extracted.raw_text,
        cleaned_text=extracted.cleaned_text,
        archived_markdown=extracted.archived_markdown,
        raw_capture_kind=extracted.raw_capture_kind,
        author=extracted.author,
        published_date=extracted.published_date,
        word_count=extracted.word_count,
        language=extracted.language,
        extraction_quality=str(extracted.extraction_quality),
        extraction_method=extracted.extraction_method,
        extraction_notes=extracted.extraction_notes,
        raw_metadata={
            **extracted.raw_metadata,
            "provider_content_mode": item.provider_content_mode.value,
            "provider": item.inbox_provider or "readwise",
            "evidence_metadata": extracted.evidence_metadata,
        },
        canonical_url=extracted.canonical_url,
        content_hash=content_hash,
        url_hash=compute_url_hash(item.url),
        derived_work_kind=item.derived_work_kind,
    )


def _record_failure(
    item: SourceItem,
    *,
    catalog_repo: SourceCatalogRepository,
    error: str,
) -> None:
    catalog = catalog_repo.upsert_source(
        CatalogSource(
            url=item.url,
            url_hash=compute_url_hash(item.url),
            source_type=item.source_type.value,
            title=item.title or item.url,
            saved_at=item.saved_at,
            metadata_status="metadata_only",
            content_status="failed",
            brief_status="not_started",
            output_status="not_published",
            failure_status="failed",
            last_failure_reason=error[:500],
        )
    )
    if item.inbox_provider:
        catalog_repo.attach_provider_ref(
            SourceProviderRef(
                source_uid=catalog.uid,
                provider=item.inbox_provider,
                external_id=item.external_id,
                external_url=item.url,
                saved_at=item.saved_at,
                title=item.title or item.url,
                metadata=item.provider_metadata,
                raw_json=_provider_raw_json(item),
            )
        )
    if item.tags:
        catalog_repo.sync_tags(catalog.uid, item.tags, origin="provider")


def _provider_raw_json(item: SourceItem) -> dict[str, Any]:
    return {
        "provider_metadata": item.provider_metadata,
        "extra": item.extra,
        "pre_extracted_content": (
            item.pre_extracted_content.model_dump() if item.pre_extracted_content else {}
        ),
    }
