from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class VaultUpdate(BaseModel):
    """Record of a file written or updated in the vault."""

    path: str
    action: str = "created"  # created | updated | unchanged
    note_type: str = ""


class IngestResult(BaseModel):
    source_url: str
    source_title: str = ""
    source_type: str = ""
    source_note_path: str = ""
    raw_capture_path: str = ""
    extraction_quality: str = ""
    extraction_method: str = ""
    bookmark_tags: list[str] = Field(default_factory=list)
    topics_updated: list[str] = Field(default_factory=list)
    entities_updated: list[str] = Field(default_factory=list)
    concepts_updated: list[str] = Field(default_factory=list)
    vault_updates: list[VaultUpdate] = Field(default_factory=list)
    deduplicated: bool = False
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class QueryResult(BaseModel):
    question: str
    answer: str = ""
    source_references: list[str] = Field(default_factory=list)
    topics_consulted: list[str] = Field(default_factory=list)
    confidence: str = "medium"
    saved_to: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LintIssue(BaseModel):
    severity: str = "warning"  # info | warning | error
    category: str = ""
    message: str = ""
    file_path: str = ""
    suggestion: str = ""


class LintResult(BaseModel):
    issues: list[LintIssue] = Field(default_factory=list)
    total_notes: int = 0
    orphan_pages: int = 0
    missing_backlinks: int = 0
    weak_pages: int = 0
    report_path: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MaintenanceTaskSummary(BaseModel):
    maintenance_class: str
    task_name: str
    status: str = "ok"
    changed_paths: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class MaintenanceResultSummary(BaseModel):
    mode: str = ""
    changed_paths: list[str] = Field(default_factory=list)
    task_results: list[MaintenanceTaskSummary] = Field(default_factory=list)
    log_path: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
