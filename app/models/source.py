from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.models.lifecycle import LifecycleMetadata


class SourceType(StrEnum):
    ARTICLE = "article"
    YOUTUBE = "youtube"
    X_THREAD = "x_thread"
    PDF = "pdf"
    GENERIC = "generic"
    DERIVED_WORK = "derived_work"


class DerivedWorkKind(StrEnum):
    DERIVED_ANALYSIS = "derived_analysis"
    SESSION_DIGEST = "session_digest"
    CRYSTALLIZED_OUTPUT = "crystallized_output"


class ExtractionQuality(StrEnum):
    FULL = "full"
    MOSTLY_FULL = "mostly_full"
    PARTIAL = "partial"
    METADATA_ONLY = "metadata_only"
    FAILED = "failed"


class SourceItem(BaseModel):
    """Metadata about a saved source before content is fetched."""

    url: str
    title: str = ""
    source_type: SourceType = SourceType.GENERIC
    tags: list[str] = Field(default_factory=list)
    saved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    inbox_provider: str = ""
    external_id: str = ""
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)
    derived_work_kind: str = ""


class SourceContent(BaseModel):
    """Fetched and normalised content for a source."""

    source: SourceItem
    raw_text: str = ""
    cleaned_text: str = ""
    archived_markdown: str = ""
    raw_capture_kind: str = ""
    author: str = ""
    published_date: str = ""
    word_count: int = 0
    language: str = "en"
    extraction_quality: str = "full"
    extraction_method: str = ""
    extraction_fallback_chain: list[str] = Field(default_factory=list)
    extraction_notes: str = ""
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
    canonical_url: str = ""
    content_hash: str = ""
    url_hash: str = ""
    derived_work_kind: str = ""
    lifecycle: LifecycleMetadata = Field(default_factory=LifecycleMetadata)
