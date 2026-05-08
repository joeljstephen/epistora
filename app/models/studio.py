from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.db import CatalogSource, ProcessingJob, SourceProviderRef, SourceTag

StudioAction = Literal["capture", "brief", "deep_compile", "refresh"]


class StudioProviderRefResponse(BaseModel):
    provider: str
    external_id: str = ""
    external_url: str = ""
    saved_at: datetime | None = None
    title: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw_json: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_ref(cls, ref: SourceProviderRef) -> "StudioProviderRefResponse":
        return cls(**ref.model_dump())


class StudioTagResponse(BaseModel):
    tag: str
    normalized_tag: str
    origin: str = "provider"

    @classmethod
    def from_tag(cls, tag: SourceTag) -> "StudioTagResponse":
        return cls(**tag.model_dump())


class StudioProcessingJobResponse(BaseModel):
    job_uid: str
    source_uid: str
    source_title: str = ""
    source_url: str = ""
    source_type: str = ""
    task_type: str
    mode: str
    status: str
    priority_score: float = 0.0
    priority_reasons: dict[str, Any] = Field(default_factory=dict)
    requested_by: str = "system"
    requested_reason: str = ""
    queued_item_id: int | None = None
    processed_source_id: int | None = None
    attempt_count: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_error: str = ""
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_job(
        cls,
        job: ProcessingJob,
        *,
        source_title: str = "",
        source_url: str = "",
        source_type: str = "",
        attempt_count: int = 0,
    ) -> "StudioProcessingJobResponse":
        payload = job.model_dump()
        payload["source_title"] = source_title
        payload["source_url"] = source_url
        payload["source_type"] = source_type
        payload["attempt_count"] = attempt_count
        return cls(**payload)


class StudioSourceSummary(BaseModel):
    uid: str
    url: str
    normalized_url: str = ""
    source_type: str = ""
    title: str = ""
    description: str = ""
    site_name: str = ""
    saved_at: datetime | None = None
    metadata_status: str
    content_status: str
    brief_status: str
    deep_status: str
    output_status: str
    failure_status: str
    last_failure_reason: str = ""
    tag_snapshot: list[str] = Field(default_factory=list)
    provider_snapshot: dict[str, Any] = Field(default_factory=dict)
    priority_score: float = 0.0
    priority_reasons: dict[str, Any] = Field(default_factory=dict)
    display_state: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_source(cls, source: CatalogSource) -> "StudioSourceSummary":
        payload = source.model_dump()
        payload["display_state"] = derive_display_state(source)
        return cls(**payload)


class StudioSourceDetail(StudioSourceSummary):
    author: str = ""
    language: str = "en"
    published_date: str = ""
    canonical_url: str = ""
    content_hash: str = ""
    source_note_path: str = ""
    raw_capture_path: str = ""
    provider_refs: list[StudioProviderRefResponse] = Field(default_factory=list)
    tags: list[StudioTagResponse] = Field(default_factory=list)
    latest_jobs: list[StudioProcessingJobResponse] = Field(default_factory=list)


class StudioSourceListResponse(BaseModel):
    sources: list[StudioSourceSummary] = Field(default_factory=list)


class StudioManualAddRequest(BaseModel):
    url: str
    title: str = ""
    tags: list[str] = Field(default_factory=list)
    enqueue_action: StudioAction | None = None


class StudioManualAddResponse(BaseModel):
    source: StudioSourceDetail
    job: StudioProcessingJobResponse | None = None


class StudioEnqueueActionRequest(BaseModel):
    action: StudioAction
    requested_reason: str = ""


class StudioProcessJobsResponse(BaseModel):
    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    jobs: list[StudioProcessingJobResponse] = Field(default_factory=list)


class StudioReadwiseSyncRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=1000)
    force: bool = False
    auto_brief_limit: int | None = Field(default=None, ge=1, le=100)


class StudioReadwiseSyncResponse(BaseModel):
    imported_count: int = 0
    failed_count: int = 0
    auto_brief_compiled_count: int = 0
    auto_brief_failed_count: int = 0


class StudioPendingBriefRequest(BaseModel):
    limit: int = Field(default=5, ge=1, le=100)
    force: bool = False


class StudioBriefCompileResponse(BaseModel):
    compiled_count: int = 0
    failed_count: int = 0


class StudioJobListResponse(BaseModel):
    jobs: list[StudioProcessingJobResponse] = Field(default_factory=list)


class StudioSourceReaderResponse(BaseModel):
    source_uid: str
    url: str
    title: str = ""
    source_type: str = ""
    description: str = ""
    author: str = ""
    site_name: str = ""
    published_date: str = ""
    saved_at: datetime | None = None
    source_note_path: str = ""
    raw_capture_path: str = ""
    source_markdown: str = ""
    raw_markdown: str = ""
    has_source_note: bool = False
    has_raw_capture: bool = False
    source_frontmatter: dict[str, Any] = Field(default_factory=dict)
    source_body: str = ""
    raw_frontmatter: dict[str, Any] = Field(default_factory=dict)
    raw_body: str = ""


class StudioKnowledgeNote(BaseModel):
    note_path: str
    note_type: str
    title: str
    snippet: str = ""
    tags: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    source_url: str = ""
    source_type: str = ""


class StudioKnowledgeListResponse(BaseModel):
    note_type: str
    notes: list[StudioKnowledgeNote] = Field(default_factory=list)


class StudioKnowledgeDetailResponse(BaseModel):
    note_path: str
    note_type: str
    title: str
    body: str = ""
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    source_url: str = ""
    source_type: str = ""


class StudioSearchHit(BaseModel):
    kind: str  # "source" or "note"
    title: str
    url: str = ""
    snippet: str = ""
    note_path: str = ""
    note_type: str = ""
    source_uid: str = ""
    source_type: str = ""
    display_state: str = ""
    score: float = 0.0
    provenance: list[str] = Field(default_factory=list)


class StudioSearchResponse(BaseModel):
    query: str
    hits: list[StudioSearchHit] = Field(default_factory=list)


class StudioStatsResponse(BaseModel):
    total_sources: int = 0
    metadata_only_sources: int = 0
    captured_sources: int = 0
    brief_ready_sources: int = 0
    deep_compiled_sources: int = 0
    failed_sources: int = 0
    queue_jobs: dict[str, int] = Field(default_factory=dict)
    queue_items: dict[str, int] = Field(default_factory=dict)
    by_source_type: dict[str, int] = Field(default_factory=dict)
    note_counts: dict[str, int] = Field(default_factory=dict)


class StudioSnapshotExportResponse(BaseModel):
    snapshot_uid: str
    snapshot_path: str
    source_count: int
    reason: str = ""


class StudioSnapshotImportRequest(BaseModel):
    snapshot_path: str


class StudioSnapshotImportResponse(BaseModel):
    imported: int


def derive_display_state(source: CatalogSource) -> str:
    if source.failure_status == "failed":
        return "failed"
    if source.deep_status == "compiled":
        return "deep_compiled"
    if source.brief_status == "ready":
        return "brief_ready"
    if source.content_status == "available":
        return "content_available"
    if source.failure_status == "partial":
        return "failed_partial"
    return "metadata_only"
