"""Canonical artifact layer for Epistora v2."""

from app.artifacts.builder import (
    artifact_id,
    build_artifact_bundle,
    canonical_name_key,
    normalize_markdown_list,
    resolve_existing_name,
)
from app.artifacts.models import (
    ArtifactBundle,
    ConceptArtifact,
    EntityArtifact,
    EvidenceReference,
    RelationshipArtifact,
    SourceArtifact,
    SynthesisArtifact,
    TopicArtifact,
)
from app.artifacts.source_brief import build_artifact_bundle_from_source_brief

__all__ = [
    "ArtifactBundle",
    "ConceptArtifact",
    "EntityArtifact",
    "EvidenceReference",
    "RelationshipArtifact",
    "SourceArtifact",
    "SynthesisArtifact",
    "TopicArtifact",
    "artifact_id",
    "build_artifact_bundle",
    "build_artifact_bundle_from_source_brief",
    "canonical_name_key",
    "normalize_markdown_list",
    "resolve_existing_name",
]
