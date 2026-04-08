"""Pydantic models for the queue-based automation system."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AutomationMode(StrEnum):
    SAFE = "safe"
    BALANCED = "balanced"
    DEEP = "deep"


class QueueItemStatus(StrEnum):
    DISCOVERED = "discovered"
    PROCESSING = "processing"
    COMPLETED = "completed"
    RETRYABLE_FAILED = "retryable_failed"
    PERMANENT_FAILED = "permanent_failed"
    SKIPPED_DUPLICATE = "skipped_duplicate"


class FailureType(StrEnum):
    NETWORK = "network"
    RATE_LIMIT = "rate_limit"
    EXTRACTION = "extraction"
    BACKEND_UNAVAILABLE = "backend_unavailable"
    TIMEOUT = "timeout"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class QueuedItem(BaseModel):
    """A bookmark discovered and staged in the durable queue."""

    id: int | None = None
    connector_id: str = ""
    external_id: str = ""
    url: str
    url_hash: str = ""
    title: str = ""
    source_type: str = ""
    tags: str = ""  # JSON array string
    saved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = QueueItemStatus.DISCOVERED
    attempt_count: int = 0
    next_attempt_at: datetime | None = None
    last_error: str = ""
    last_error_type: str = ""
    mode_last_attempted: str = ""
    backend_last_used: str = ""
    processed_source_id: int | None = None
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AutomationRun(BaseModel):
    """Record of an automation run."""

    id: int | None = None
    run_type: str = ""  # discover | process | maintain | full
    mode: str = AutomationMode.SAFE
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    items_discovered: int = 0
    items_processed: int = 0
    items_failed: int = 0
    items_skipped: int = 0
    maintenance_ran: bool = False
    error: str = ""
    summary: str = ""


class ItemAttempt(BaseModel):
    """Record of a single processing attempt for a queued item."""

    id: int | None = None
    queued_item_id: int
    attempt_number: int = 1
    mode: str = AutomationMode.SAFE
    backend_used: str = ""
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    success: bool = False
    error: str = ""
    error_type: str = ""


class DiscoverResult(BaseModel):
    """Result from a discover operation."""

    items_discovered: int = 0
    items_skipped_duplicate: int = 0
    connector_id: str = ""
    error: str = ""


class ProcessResult(BaseModel):
    """Result from processing a single queued item."""

    queued_item_id: int
    success: bool = False
    mode: str = ""
    backend_used: str = ""
    error: str = ""
    error_type: str = ""
    source_note_path: str = ""
    raw_capture_path: str = ""


class AutomationStatus(BaseModel):
    """Overall automation system status."""

    automation_enabled: bool = False
    default_mode: str = AutomationMode.SAFE
    connectors: dict[str, dict[str, Any]] = Field(default_factory=dict)
    queue_counts: dict[str, int] = Field(default_factory=dict)
    last_run: AutomationRun | None = None
    retryable_failures: int = 0
    backends_available: dict[str, bool] = Field(default_factory=dict)
