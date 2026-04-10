"""Shared lifecycle metadata hooks for sources and artifacts."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class StalenessStatus(StrEnum):
    CURRENT = "current"
    NEEDS_REVIEW = "needs_review"
    STALE = "stale"
    UNKNOWN = "unknown"


class LifecycleMetadata(BaseModel):
    """Minimal migration-friendly lifecycle fields.

    These are structural hooks only. They do not imply a full confidence,
    retention, or supersession engine yet.
    """

    confidence: float | None = None
    last_confirmed_at: str = ""
    supersedes: list[str] = Field(default_factory=list)
    superseded_by: list[str] = Field(default_factory=list)
    staleness_status: str = StalenessStatus.UNKNOWN
    reinforcement_count: int = 0

    def as_frontmatter(self) -> dict[str, object]:
        return self.model_dump(mode="json")
