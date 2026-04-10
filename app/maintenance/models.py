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


class MaintenanceTask(BaseModel):
    """A single planned maintenance task."""

    maintenance_class: str
    task_name: str
    scope_paths: list[str] = Field(default_factory=list)
    max_items: int = 0
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
