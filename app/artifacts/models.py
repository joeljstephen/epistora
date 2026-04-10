"""Canonical internal artifact models for the v2 compiler layer."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EvidenceReference(BaseModel):
    """Traceable support pointing back to preserved source evidence."""

    id: str
    source_id: str
    raw_ref: str
    excerpt: str = ""
    offset_or_section: str = ""
    confidence: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class RelationshipArtifact(BaseModel):
    """Explicit relationship between canonical artifacts."""

    id: str
    relationship_type: str
    from_artifact_id: str
    to_artifact_id: str
    source_artifact_id: str = ""
    evidence_reference_ids: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceArtifact(BaseModel):
    """Structured understanding of a single compiled source."""

    id: str
    slug: str
    title: str
    source_type: str
    source_url: str
    canonical_url: str = ""
    author: str = ""
    published_at: str = ""
    summary: str = ""
    five_minute_read: str = ""
    detailed_note: str = ""
    key_ideas: list[str] = Field(default_factory=list)
    detailed_outline: str = ""
    examples: list[str] = Field(default_factory=list)
    takeaways: list[str] = Field(default_factory=list)
    quotes: list[str] = Field(default_factory=list)
    best_for: list[str] = Field(default_factory=list)
    consume_recommendation: str = ""
    why_it_matters: str = ""
    open_questions: list[str] = Field(default_factory=list)
    topic_ids: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    concept_ids: list[str] = Field(default_factory=list)
    relationship_ids: list[str] = Field(default_factory=list)
    evidence_reference_ids: list[str] = Field(default_factory=list)
    quality: str = ""
    trust_class: str = "unknown"
    extraction_method: str = ""
    extraction_fallback_chain: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    word_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class TopicArtifact(BaseModel):
    """Canonical topic artifact built before markdown rendering."""

    id: str
    slug: str
    title: str
    summary: str = ""
    source_artifact_ids: list[str] = Field(default_factory=list)
    related_topic_ids: list[str] = Field(default_factory=list)
    related_entity_ids: list[str] = Field(default_factory=list)
    related_concept_ids: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EntityArtifact(BaseModel):
    """Canonical entity artifact built before markdown rendering."""

    id: str
    slug: str
    title: str
    entity_type: str = "unknown"
    summary: str = ""
    contexts: list[str] = Field(default_factory=list)
    source_artifact_ids: list[str] = Field(default_factory=list)
    related_concept_ids: list[str] = Field(default_factory=list)
    related_topic_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConceptArtifact(BaseModel):
    """Canonical concept artifact built before markdown rendering."""

    id: str
    slug: str
    title: str
    definition: str = ""
    examples: list[str] = Field(default_factory=list)
    related_concept_ids: list[str] = Field(default_factory=list)
    source_artifact_ids: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SynthesisArtifact(BaseModel):
    """Durable cross-source synthesis artifact."""

    id: str
    slug: str
    title: str
    summary: str = ""
    source_basis_ids: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)
    disagreements: list[str] = Field(default_factory=list)
    reusable_takeaways: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactBundle(BaseModel):
    """Canonical compiler output passed to renderers/sinks."""

    source: SourceArtifact
    topics: list[TopicArtifact] = Field(default_factory=list)
    entities: list[EntityArtifact] = Field(default_factory=list)
    concepts: list[ConceptArtifact] = Field(default_factory=list)
    relationships: list[RelationshipArtifact] = Field(default_factory=list)
    synthesis: list[SynthesisArtifact] = Field(default_factory=list)
    evidence_references: list[EvidenceReference] = Field(default_factory=list)

    def artifact_index(
        self,
    ) -> dict[
        str,
        SourceArtifact | TopicArtifact | EntityArtifact | ConceptArtifact | SynthesisArtifact,
    ]:
        artifacts: dict[
            str,
            SourceArtifact | TopicArtifact | EntityArtifact | ConceptArtifact | SynthesisArtifact,
        ] = {self.source.id: self.source}
        for collection in (self.topics, self.entities, self.concepts, self.synthesis):
            for artifact in collection:
                artifacts[artifact.id] = artifact
        return artifacts
