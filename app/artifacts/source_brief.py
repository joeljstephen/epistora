"""Build canonical artifacts from the v1 Source Brief contract."""

from __future__ import annotations

from app.artifacts.builder import build_artifact_bundle
from app.artifacts.models import ArtifactBundle
from app.models.source import SourceContent
from app.models.source_brief import SourceBrief, source_brief_to_analysis


def build_artifact_bundle_from_source_brief(
    *,
    content: SourceContent,
    slug: str,
    brief: SourceBrief,
    existing_lookup: dict[str, dict[str, str]] | None = None,
) -> ArtifactBundle:
    return build_artifact_bundle(
        content=content,
        slug=slug,
        analysis=source_brief_to_analysis(brief),
        existing_lookup=existing_lookup,
    )
