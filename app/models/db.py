from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ProcessedSource(BaseModel):
    id: int | None = None
    url: str
    url_hash: str
    content_hash: str = ""
    source_type: str = ""
    title: str = ""
    source_note_path: str = ""
    raw_capture_path: str = ""
    provider: str = ""
    external_id: str = ""
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    status: str = "completed"
    error_message: str = ""
    retry_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SyncCursor(BaseModel):
    connector: str
    last_sync_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cursor_value: str = ""


class VaultNoteMapping(BaseModel):
    note_path: str
    note_type: str  # source | topic | entity | concept | synthesis
    slug: str = ""
    title: str = ""
    source_url: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SourceMetadataStatus(StrEnum):
    METADATA_ONLY = "metadata_only"
    CAPTURED = "captured"


class SourceContentStatus(StrEnum):
    NOT_FETCHED = "not_fetched"
    AVAILABLE = "available"
    FAILED = "failed"


class SourceBriefStatus(StrEnum):
    NOT_STARTED = "not_started"
    PARTIAL = "partial"
    READY = "ready"
    FAILED = "failed"


class SourceDeepStatus(StrEnum):
    NOT_STARTED = "not_started"
    COMPILED = "compiled"
    FAILED = "failed"


class SourceOutputStatus(StrEnum):
    NOT_PUBLISHED = "not_published"
    PUBLISHED = "published"


class SourceFailureStatus(StrEnum):
    NONE = "none"
    PARTIAL = "partial"
    FAILED = "failed"


class SourceTagOrigin(StrEnum):
    PROVIDER = "provider"
    USER = "user"
    SYSTEM = "system"
    THEME = "theme"


class ProcessingJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class ProcessingTaskType(StrEnum):
    CAPTURE = "capture"
    BRIEF = "brief"
    DEEP_COMPILE = "deep_compile"
    REFRESH = "refresh"


class CatalogSource(BaseModel):
    id: int | None = None
    uid: str = ""
    url: str
    normalized_url: str = ""
    url_hash: str = ""
    canonical_url: str = ""
    canonical_url_hash: str = ""
    content_hash: str = ""
    source_type: str = ""
    title: str = ""
    description: str = ""
    author: str = ""
    site_name: str = ""
    language: str = "en"
    published_date: str = ""
    saved_at: datetime | None = None
    metadata_status: str = SourceMetadataStatus.METADATA_ONLY
    content_status: str = SourceContentStatus.NOT_FETCHED
    brief_status: str = SourceBriefStatus.NOT_STARTED
    deep_status: str = SourceDeepStatus.NOT_STARTED
    output_status: str = SourceOutputStatus.NOT_PUBLISHED
    failure_status: str = SourceFailureStatus.NONE
    last_failure_reason: str = ""
    tag_snapshot: list[str] = Field(default_factory=list)
    provider_snapshot: dict[str, Any] = Field(default_factory=dict)
    priority_score: float = 0.0
    priority_reasons: dict[str, Any] = Field(default_factory=dict)
    priority_policy_version: str = ""
    priority_computed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SourceProviderRef(BaseModel):
    id: int | None = None
    source_uid: str
    provider: str
    external_id: str = ""
    external_url: str = ""
    external_created_at: datetime | None = None
    external_updated_at: datetime | None = None
    saved_at: datetime | None = None
    title: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw_json: dict[str, Any] = Field(default_factory=dict)
    first_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SourceTag(BaseModel):
    id: int | None = None
    source_uid: str
    tag: str
    normalized_tag: str
    origin: str = SourceTagOrigin.PROVIDER
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProcessingJob(BaseModel):
    id: int | None = None
    job_uid: str = ""
    source_uid: str
    task_type: str
    mode: str = "safe"
    status: str = ProcessingJobStatus.QUEUED
    priority_score: float = 0.0
    priority_reasons: dict[str, Any] = Field(default_factory=dict)
    priority_policy_version: str = ""
    requested_by: str = "system"
    requested_reason: str = ""
    queued_item_id: int | None = None
    processed_source_id: int | None = None
    run_after: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_error: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProcessingAttempt(BaseModel):
    id: int | None = None
    job_uid: str
    attempt_number: int = 1
    backend_used: str = ""
    model_used: str = ""
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    success: bool = False
    error: str = ""
    error_type: str = ""
    usage_event_uid: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UsageEvent(BaseModel):
    id: int | None = None
    event_uid: str = ""
    source_uid: str = ""
    job_uid: str = ""
    attempt_id: int | None = None
    task_type: str = ""
    backend: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0
    budget_bucket: str = "global"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SourceCatalogSnapshot(BaseModel):
    id: int | None = None
    snapshot_uid: str = ""
    snapshot_path: str = ""
    source_count: int = 0
    reason: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
