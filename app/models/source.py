from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class SourceType(StrEnum):
    ARTICLE = "article"
    YOUTUBE = "youtube"
    X_THREAD = "x_thread"
    PDF = "pdf"
    GENERIC = "generic"


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
    raindrop_id: int | None = None
    collection_id: int | None = None
    extra: dict = Field(default_factory=dict)


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
    raw_metadata: dict = Field(default_factory=dict)
    canonical_url: str = ""
    content_hash: str = ""
    url_hash: str = ""
