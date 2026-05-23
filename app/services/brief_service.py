"""Compile pending Source Briefs into vault source notes."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.artifacts.source_brief import build_artifact_bundle_from_source_brief
from app.backends.models import TaskName
from app.compiler.llm import run_structured
from app.config import get_settings
from app.models.db import (
    CatalogSource,
    ProcessedSource,
    ProcessingAttempt,
    VaultNoteMapping,
)
from app.models.source import SourceContent, SourceItem, SourceType
from app.models.source_brief import (
    source_brief_json_schema,
    validate_source_brief,
)
from app.models.source_lifecycle import apply_transition, brief_failed, brief_published
from app.sinks.markdown_vault import MarkdownVaultSink
from app.storage.evidence import evidence_storage_policy_from_settings
from app.storage.repositories import (
    SourceCatalogRepository,
    SourceRepository,
    VaultNoteRepository,
)
from app.storage.sqlite import Database
from app.utils.hashing import url_hash as compute_url_hash
from app.utils.markdown import parse_markdown_file
from app.utils.slugify import slugify
from app.vault.paths import raw_capture_path

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[str, dict[str, Any]], None]


@dataclass(frozen=True)
class CompiledBriefSource:
    source_uid: str
    source_note_path: str
    raw_capture_path: str


@dataclass(frozen=True)
class BriefCompilationResult:
    compiled: list[CompiledBriefSource] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    @property
    def compiled_count(self) -> int:
        return len(self.compiled)

    @property
    def failed_count(self) -> int:
        return len(self.failures)


async def compile_pending_source_briefs(
    *,
    limit: int = 5,
    force: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> BriefCompilationResult:
    """Compile content-ready Sources into Source Brief notes."""
    settings = get_settings()
    db = Database(settings.db_path)
    db.connect()
    catalog_repo = SourceCatalogRepository(db)
    source_repo = SourceRepository(db)
    note_repo = VaultNoteRepository(db)
    sink = MarkdownVaultSink(
        Path(settings.vault_path),
        storage_policy=evidence_storage_policy_from_settings(settings),
    )
    sink.ensure_structure()

    compiled: list[CompiledBriefSource] = []
    failures: list[str] = []

    try:
        _emit_progress(progress_callback, "brief_compile_start", limit=limit, force=force)
        candidates = _pending_sources(catalog_repo, limit=limit, force=force)
        for source in candidates:
            try:
                compiled.append(
                    await _compile_source(
                        source,
                        vault_path=Path(settings.vault_path),
                        catalog_repo=catalog_repo,
                        source_repo=source_repo,
                        note_repo=note_repo,
                        sink=sink,
                    )
                )
            except Exception as exc:
                logger.warning("Brief compilation failed for %s: %s", source.url, exc)
                apply_transition(catalog_repo, source.uid, brief_failed(str(exc)))
                failures.append(f"{source.url}: {exc}")

        _emit_progress(
            progress_callback,
            "brief_compile_done",
            compiled_count=len(compiled),
            failed_count=len(failures),
        )
        return BriefCompilationResult(compiled=compiled, failures=failures)
    finally:
        db.close()


async def compile_source_brief(
    source_uid: str,
    *,
    force: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> BriefCompilationResult:
    """Compile or recompile one catalog Source into a Source Brief note."""
    settings = get_settings()
    db = Database(settings.db_path)
    db.connect()
    catalog_repo = SourceCatalogRepository(db)
    source_repo = SourceRepository(db)
    note_repo = VaultNoteRepository(db)
    sink = MarkdownVaultSink(
        Path(settings.vault_path),
        storage_policy=evidence_storage_policy_from_settings(settings),
    )
    sink.ensure_structure()

    try:
        source = catalog_repo.get_source(source_uid)
        if source is None:
            raise ValueError(f"Source '{source_uid}' does not exist")
        if not force and source.brief_status == "ready":
            return BriefCompilationResult()
        if source.content_status != "available":
            raise ValueError(f"Source '{source_uid}' does not have available content")

        _emit_progress(progress_callback, "brief_compile_start", limit=1, force=force)
        try:
            compiled = await _compile_source(
                source,
                vault_path=Path(settings.vault_path),
                catalog_repo=catalog_repo,
                source_repo=source_repo,
                note_repo=note_repo,
                sink=sink,
            )
        except Exception as exc:
            logger.warning("Brief compilation failed for %s: %s", source.url, exc)
            apply_transition(catalog_repo, source.uid, brief_failed(str(exc)))
            _emit_progress(
                progress_callback,
                "brief_compile_done",
                compiled_count=0,
                failed_count=1,
            )
            return BriefCompilationResult(failures=[f"{source.url}: {exc}"])

        _emit_progress(
            progress_callback,
            "brief_compile_done",
            compiled_count=1,
            failed_count=0,
        )
        return BriefCompilationResult(compiled=[compiled])
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
        logger.debug("Brief progress callback failed for stage=%s", stage, exc_info=True)


def _pending_sources(
    catalog_repo: SourceCatalogRepository,
    *,
    limit: int,
    force: bool,
) -> list[CatalogSource]:
    if force:
        return catalog_repo.list_sources(limit=limit)
    return catalog_repo.list_sources(limit=limit, display_state="content_available")


async def _compile_source(
    source: CatalogSource,
    *,
    vault_path: Path,
    catalog_repo: SourceCatalogRepository,
    source_repo: SourceRepository,
    note_repo: VaultNoteRepository,
    sink: MarkdownVaultSink,
) -> CompiledBriefSource:
    content, slug, raw_rel_path = _source_content_from_catalog(source, vault_path=vault_path)
    schema = json.dumps(source_brief_json_schema(content.source.source_type))
    response = await run_structured(
        TaskName.INGEST,
        _brief_system_prompt(content.source.source_type),
        _brief_user_prompt(content),
        json_schema_hint=schema,
    )
    if not response.success:
        raise ValueError(response.error or "Backend failed to compile Source Brief")

    payload = json.loads(response.text)
    brief = validate_source_brief(
        payload,
        source_type=content.source.source_type,
        content=content,
    )
    bundle = build_artifact_bundle_from_source_brief(content=content, slug=slug, brief=brief)
    updates = sink.publish(content=content, bundle=bundle)

    source_note_path = ""
    published_raw_path = raw_rel_path
    for update in updates:
        if update.note_type == "source":
            source_note_path = update.path
        elif update.note_type == "raw_capture":
            published_raw_path = update.path
        if update.note_type in {"source", "topic", "entity", "concept", "synthesis"}:
            note_repo.upsert(
                VaultNoteMapping(
                    note_path=update.path,
                    note_type=update.note_type,
                    slug=slug if update.note_type == "source" else "",
                    title=content.source.title if update.note_type == "source" else "",
                    source_url=content.source.url if update.note_type == "source" else "",
                )
            )

    apply_transition(
        catalog_repo,
        source.uid,
        brief_published(content_hash=content.content_hash),
    )
    source_repo.upsert(
        ProcessedSource(
            url=content.source.url,
            url_hash=content.url_hash or compute_url_hash(content.source.url),
            content_hash=content.content_hash,
            source_type=content.source.source_type.value,
            title=content.source.title,
            source_note_path=source_note_path,
            raw_capture_path=published_raw_path,
            provider=content.source.inbox_provider,
            external_id=content.source.external_id,
            provider_metadata=content.source.provider_metadata,
            status="completed",
        )
    )
    catalog_repo.record_processing_attempt(
        ProcessingAttempt(
            job_uid=f"brief:{source.uid}",
            backend_used=str(response.backend_used or ""),
            model_used=response.model_used,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            success=True,
        )
    )
    return CompiledBriefSource(
        source_uid=source.uid,
        source_note_path=source_note_path,
        raw_capture_path=published_raw_path,
    )


def _source_content_from_catalog(
    source: CatalogSource,
    *,
    vault_path: Path,
) -> tuple[SourceContent, str, str]:
    source_type = SourceType(source.source_type or SourceType.GENERIC)
    slug = slugify(source.title or source.url) or source.url_hash
    raw_path = raw_capture_path(vault_path, source_type, slug)
    meta, body = parse_markdown_file(raw_path)
    if not body:
        raise ValueError(f"Raw Capture not found for pending Source: {raw_path}")

    item = SourceItem(
        url=source.url,
        title=source.title or source.url,
        source_type=source_type,
        tags=list(source.tag_snapshot),
        saved_at=source.saved_at or datetime.now(timezone.utc),
        inbox_provider=_provider_id(source),
        external_id=_external_id(source),
        provider_metadata=dict(source.provider_snapshot),
    )
    content = SourceContent(
        source=item,
        raw_text=body,
        cleaned_text=body,
        raw_capture_kind=str(meta.get("raw_capture_kind", "") or ""),
        author=source.author,
        published_date=source.published_date,
        word_count=int(source.priority_reasons.get("word_count", 0) or 0),
        extraction_quality=str(meta.get("extraction_quality", "") or "full"),
        extraction_method=str(meta.get("extraction_method", "") or ""),
        raw_metadata={key: value for key, value in meta.items() if isinstance(key, str)},
        canonical_url=source.canonical_url,
        content_hash=source.content_hash,
        url_hash=source.url_hash,
    )
    return content, slug, str(raw_path.relative_to(vault_path))


def _brief_system_prompt(source_type: SourceType) -> str:
    return (
        "You compile Epistora Source Briefs. Return only JSON matching the "
        f"{source_type.value} Source Brief schema."
    )


def _brief_user_prompt(content: SourceContent) -> str:
    evidence = (content.cleaned_text or content.raw_text)[:16000]
    return "\n".join(
        [
            f"Title: {content.source.title}",
            f"URL: {content.source.url}",
            f"SourceType: {content.source.source_type.value}",
            "",
            "Evidence:",
            evidence,
        ]
    )


def _provider_id(source: CatalogSource) -> str:
    if source.provider_snapshot:
        return next(iter(source.provider_snapshot.keys()))
    return ""


def _external_id(source: CatalogSource) -> str:
    provider = _provider_id(source)
    if not provider:
        return ""
    value = source.provider_snapshot.get(provider, {})
    if isinstance(value, dict):
        return str(value.get("external_id") or "")
    return ""
