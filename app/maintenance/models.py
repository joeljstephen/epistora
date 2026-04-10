"""Models for the maintenance planning and execution framework."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class MaintenanceClass(StrEnum):
    STRUCTURAL = "structural"
    SEMANTIC = "semantic"
    SYNTHESIS = "synthesis"
    STORAGE = "storage"


class MaintenanceTrigger(StrEnum):
    MANUAL_SCOPE = "manual_scope"
    POST_INGEST = "post_ingest"
    DEEP_MODE = "deep_mode"
    FORCE_REBUILD = "force_rebuild"
    AUTOMATION_TICK = "automation_tick"


class MaintenanceTaskName(StrEnum):
    ARTIFACT_NEIGHBORHOOD_REFRESH = "artifact_neighborhood_refresh"
    STRUCTURAL_REPAIR = "structural_repair"
    HUB_REFRESH = "hub_refresh"
    BACKLINK_REPAIR = "backlink_repair"
    CANDIDATE_SYNTHESIS_REFRESH = "candidate_synthesis_refresh"
    READ_MODEL_REFRESH = "read_model_refresh"
    SEARCH_REFRESH = "search_refresh"


class MaintenanceTask(BaseModel):
    """A single planned maintenance task."""

    maintenance_class: str
    task_name: str
    trigger: str = MaintenanceTrigger.MANUAL_SCOPE
    scope_paths: list[str] = Field(default_factory=list)
    max_items: int = 0
    writes_enabled: bool = False
    write_scope: str = ""
    idempotent: bool = True
    details: dict[str, Any] = Field(default_factory=dict)


class MaintenancePlan(BaseModel):
    """A bounded maintenance plan for a vault run."""

    mode: str
    scope_paths: list[str] = Field(default_factory=list)
    neighborhood_paths: list[str] = Field(default_factory=list)
    tasks: list[MaintenanceTask] = Field(default_factory=list)


class MaintenanceTaskResult(BaseModel):
    """Execution result for one maintenance task."""

    maintenance_class: str
    task_name: str
    status: str = "ok"
    trigger: str = ""
    scope_paths: list[str] = Field(default_factory=list)
    changed_paths: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    error: str = ""


class MaintenanceResult(BaseModel):
    """Summary of a maintenance run."""

    mode: str
    scope_paths: list[str] = Field(default_factory=list)
    planned_tasks: list[str] = Field(default_factory=list)
    task_results: list[MaintenanceTaskResult] = Field(default_factory=list)
    changed_paths: list[str] = Field(default_factory=list)
    log_path: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
