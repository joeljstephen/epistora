from __future__ import annotations

from app.models.db import CatalogSource
from app.models.source_lifecycle import (
    apply_transition,
    brief_failed,
    brief_published,
    capture_published,
    deep_compiled,
    derive_display_state,
    partial_failure,
)
from app.storage.repositories import SourceCatalogRepository


def test_source_lifecycle_transitions_drive_display_state(tmp_db):
    repo = SourceCatalogRepository(tmp_db)
    source = repo.upsert_source(CatalogSource(url="https://example.com/a", title="A"))

    captured = apply_transition(repo, source.uid, capture_published(content_hash="hash-a"))
    assert captured.metadata_status == "captured"
    assert captured.content_status == "available"
    assert captured.brief_status == "partial"
    assert captured.output_status == "published"
    assert derive_display_state(captured) == "content_available"

    briefed = apply_transition(repo, source.uid, brief_published(content_hash="hash-b"))
    assert briefed.brief_status == "ready"
    assert derive_display_state(briefed) == "brief_ready"

    deep = apply_transition(repo, source.uid, deep_compiled(content_hash="hash-c"))
    assert deep.deep_status == "compiled"
    assert derive_display_state(deep) == "deep_compiled"


def test_source_lifecycle_failure_precedence(tmp_db):
    repo = SourceCatalogRepository(tmp_db)
    source = repo.upsert_source(CatalogSource(url="https://example.com/b", title="B"))
    source = apply_transition(repo, source.uid, brief_published(content_hash="hash-b"))

    partial = apply_transition(repo, source.uid, partial_failure("temporary extraction issue"))
    assert partial.failure_status == "partial"
    assert partial.last_failure_reason == "temporary extraction issue"
    assert derive_display_state(partial) == "failed_partial"
    assert repo.list_sources(display_state="failed_partial")[0].uid == source.uid
    assert repo.list_sources(display_state="brief_ready") == []

    failed = apply_transition(repo, source.uid, brief_failed("backend unavailable"))
    assert failed.brief_status == "failed"
    assert failed.failure_status == "failed"
    assert derive_display_state(failed) == "failed"
    assert repo.list_sources(display_state="failed")[0].uid == source.uid
