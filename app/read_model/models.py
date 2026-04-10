"""Typed models for the derived local read model."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class ReadModelNote(BaseModel):
    note_path: str
    note_type: str
    title: str
    source_url: str = ""
    source_type: str = ""
    extraction_quality: str = ""
    tags: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    concepts: list[str] = Field(default_factory=list)
    outgoing_links: list[str] = Field(default_factory=list)
    file_mtime_ns: int = 0
    indexed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReadModelEdge(BaseModel):
    from_note_path: str
    to_note_path: str = ""
    relation_type: str
    target_title: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    indexed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
