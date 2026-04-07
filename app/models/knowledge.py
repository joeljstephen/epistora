from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Topic(BaseModel):
    name: str
    slug: str = ""
    summary: str = ""
    source_ids: list[str] = Field(default_factory=list)
    related_concepts: list[str] = Field(default_factory=list)
    related_entities: list[str] = Field(default_factory=list)


class Entity(BaseModel):
    name: str
    slug: str = ""
    entity_type: str = "unknown"  # person, company, tool, etc.
    description: str = ""
    source_ids: list[str] = Field(default_factory=list)
    related_concepts: list[str] = Field(default_factory=list)


class Concept(BaseModel):
    name: str
    slug: str = ""
    definition: str = ""
    source_ids: list[str] = Field(default_factory=list)
    related_concepts: list[str] = Field(default_factory=list)


class SynthesisNote(BaseModel):
    title: str
    slug: str = ""
    summary: str = ""
    source_basis: list[str] = Field(default_factory=list)
    main_patterns: str = ""
    conflicts: str = ""
    next_steps: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
