"""Build canonical artifacts from extracted evidence and analysis."""

from __future__ import annotations

import re
from typing import Any

from app.artifacts.models import (
    ArtifactBundle,
    ConceptArtifact,
    EntityArtifact,
    EvidenceReference,
    RelationshipArtifact,
    SourceArtifact,
    TopicArtifact,
)
from app.models.lifecycle import LifecycleMetadata, StalenessStatus
from app.models.source import SourceContent
from app.utils.slugify import slugify
from app.utils.theme_tags import assign_theme_tags

_BULLET_PREFIXES = ("- ", "* ", "• ", "→ ", "=> ", "-> ")


def artifact_id(kind: str, slug: str) -> str:
    return f"{kind}:{slug}"


def canonical_name_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def resolve_existing_name(existing: dict[str, str], name: str) -> str:
    return existing.get(slugify(name)) or existing.get(canonical_name_key(name)) or name


def normalize_markdown_list(value: str | list[str] | None) -> list[str]:
    """Normalize bullets, paragraphs, or arrays into a clean string list."""
    if value is None:
        return []

    if isinstance(value, list):
        candidates = [str(item).strip() for item in value]
    else:
        text = value.strip()
        if not text:
            return []
        candidates = []
        blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
        for block in blocks:
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            current: list[str] = []
            for line in lines:
                if line.startswith("## "):
                    continue
                if line.startswith(_BULLET_PREFIXES):
                    if current:
                        candidates.append(" ".join(current).strip())
                    current = [_strip_bullet(line)]
                    continue
                if re.match(r"^\d+\.\s+", line):
                    if current:
                        candidates.append(" ".join(current).strip())
                    current = [re.sub(r"^\d+\.\s+", "", line).strip()]
                    continue
                if current:
                    current.append(line)
                else:
                    current = [line]
            if current:
                candidates.append(" ".join(current).strip())

    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        clean = _clean_list_item(candidate)
        if not clean or clean in seen:
            continue
        seen.add(clean)
        normalized.append(clean)
    return normalized


def render_markdown_list(items: list[str], empty: str) -> str:
    return "\n".join(f"- {item}" for item in items) if items else empty


def build_artifact_bundle(
    *,
    content: SourceContent,
    slug: str,
    analysis: dict[str, Any],
    existing_lookup: dict[str, dict[str, str]] | None = None,
) -> ArtifactBundle:
    existing_lookup = existing_lookup or {"topic": {}, "entity": {}, "concept": {}}
    source_id = artifact_id("source", slug)

    evidence_references = _build_evidence_references(content, source_id)
    evidence_ids = [ref.id for ref in evidence_references]

    topics = _build_topic_artifacts(analysis, slug, source_id, existing_lookup)
    entities = _build_entity_artifacts(analysis, slug, source_id, existing_lookup)
    concepts = _build_concept_artifacts(analysis, slug, source_id, existing_lookup)
    relationships = _build_relationships(
        source_id=source_id,
        topic_artifacts=topics,
        entity_artifacts=entities,
        concept_artifacts=concepts,
        evidence_reference_ids=evidence_ids,
    )

    source = SourceArtifact(
        id=source_id,
        slug=slug,
        title=content.source.title or content.source.url,
        source_type=content.source.source_type.value,
        source_url=content.source.url,
        derived_work_kind=content.derived_work_kind or content.source.derived_work_kind,
        canonical_url=content.canonical_url,
        author=content.author,
        published_at=content.published_date,
        quick_brief=_text_value(analysis.get("quick_brief")),
        summary=analysis.get("summary", "").strip(),
        five_minute_read=analysis.get("five_minute_read", "").strip(),
        detailed_note=analysis.get("detailed_reading_note", "").strip(),
        best_next_action=_text_value(analysis.get("best_next_action")),
        theme_tags=_theme_tags(content, analysis),
        brief_status=_brief_status(content, analysis),
        watch_verdict=_text_value(analysis.get("watch_verdict")),
        watch_verdict_reasoning=_text_value(analysis.get("watch_verdict_reasoning")),
        quick_section_guide=_text_value(analysis.get("quick_section_guide")),
        detailed_sections=_text_value(analysis.get("detailed_sections")),
        signal_vs_filler=_text_value(analysis.get("signal_vs_filler")),
        important_terms=_important_terms(analysis),
        key_ideas=normalize_markdown_list(analysis.get("key_ideas")),
        detailed_outline=analysis.get("detailed_outline", "").strip(),
        examples=normalize_markdown_list(analysis.get("important_examples")),
        takeaways=normalize_markdown_list(analysis.get("actionable_takeaways")),
        quotes=normalize_markdown_list(analysis.get("notable_quotes")),
        best_for=normalize_markdown_list(analysis.get("best_for")),
        consume_recommendation=analysis.get("consume_recommendation", "").strip(),
        why_it_matters=analysis.get("why_it_matters", "").strip(),
        open_questions=normalize_markdown_list(analysis.get("open_questions")),
        topic_ids=[artifact.id for artifact in topics],
        entity_ids=[artifact.id for artifact in entities],
        concept_ids=[artifact.id for artifact in concepts],
        relationship_ids=[artifact.id for artifact in relationships],
        evidence_reference_ids=evidence_ids,
        quality=content.extraction_quality,
        extraction_method=content.extraction_method,
        extraction_fallback_chain=list(content.extraction_fallback_chain),
        tags=list(content.source.tags),
        word_count=content.word_count,
        lifecycle=_source_lifecycle(content),
        metadata={
            "extraction_notes": content.extraction_notes,
            "raw_capture_kind": content.raw_capture_kind,
            "raw_metadata": dict(content.raw_metadata),
        },
    )

    return ArtifactBundle(
        source=source,
        topics=topics,
        entities=entities,
        concepts=concepts,
        relationships=relationships,
        synthesis=[],
        evidence_references=evidence_references,
    )


def _build_topic_artifacts(
    analysis: dict[str, Any],
    slug: str,
    source_id: str,
    existing_lookup: dict[str, dict[str, str]],
) -> list[TopicArtifact]:
    topic_artifacts: list[TopicArtifact] = []
    entity_ids: list[str] = []
    concept_ids: list[str] = []
    for entity in analysis.get("entities", []):
        if isinstance(entity, dict):
            entity_name = resolve_existing_name(existing_lookup["entity"], entity.get("name", ""))
        else:
            entity_name = resolve_existing_name(existing_lookup["entity"], str(entity))
        if entity_name:
            entity_ids.append(artifact_id("entity", slugify(entity_name)))
    for concept in analysis.get("concepts", []):
        if isinstance(concept, dict):
            concept_name = resolve_existing_name(
                existing_lookup["concept"], concept.get("name", "")
            )
        else:
            concept_name = resolve_existing_name(existing_lookup["concept"], str(concept))
        if concept_name:
            concept_ids.append(artifact_id("concept", slugify(concept_name)))

    for topic_name in analysis.get("topics", []):
        resolved = resolve_existing_name(existing_lookup["topic"], str(topic_name))
        topic_slug = slugify(resolved)
        topic_artifacts.append(
            TopicArtifact(
                id=artifact_id("topic", topic_slug),
                slug=topic_slug,
                title=resolved,
                summary=analysis.get("summary", "").strip(),
                source_artifact_ids=[source_id],
                related_entity_ids=list(dict.fromkeys(entity_ids)),
                related_concept_ids=list(dict.fromkeys(concept_ids)),
                lifecycle=LifecycleMetadata(
                    confidence=0.5,
                    staleness_status=StalenessStatus.UNKNOWN,
                    reinforcement_count=1,
                ),
            )
        )
    return topic_artifacts


def _build_entity_artifacts(
    analysis: dict[str, Any],
    slug: str,
    source_id: str,
    existing_lookup: dict[str, dict[str, str]],
) -> list[EntityArtifact]:
    topic_ids: list[str] = []
    for topic_name in analysis.get("topics", []):
        if not str(topic_name).strip():
            continue
        resolved_topic = resolve_existing_name(existing_lookup["topic"], str(topic_name))
        topic_ids.append(artifact_id("topic", slugify(resolved_topic)))

    concept_ids: list[str] = []
    for concept in analysis.get("concepts", []):
        if isinstance(concept, dict):
            concept_name = resolve_existing_name(
                existing_lookup["concept"], concept.get("name", "")
            )
        else:
            concept_name = resolve_existing_name(existing_lookup["concept"], str(concept))
        if concept_name:
            concept_ids.append(artifact_id("concept", slugify(concept_name)))

    entities: list[EntityArtifact] = []
    for entity_data in analysis.get("entities", []):
        if isinstance(entity_data, str):
            entity_data = {"name": entity_data, "type": "unknown", "description": ""}
        resolved = resolve_existing_name(existing_lookup["entity"], entity_data.get("name", ""))
        entity_slug = slugify(resolved)
        entities.append(
            EntityArtifact(
                id=artifact_id("entity", entity_slug),
                slug=entity_slug,
                title=resolved,
                entity_type=entity_data.get("type", "unknown") or "unknown",
                summary=entity_data.get("description", "").strip(),
                contexts=[f"mentioned_in:{slug}"],
                source_artifact_ids=[source_id],
                related_concept_ids=list(dict.fromkeys(concept_ids)),
                related_topic_ids=list(dict.fromkeys(topic_ids)),
                lifecycle=LifecycleMetadata(
                    confidence=0.5,
                    staleness_status=StalenessStatus.UNKNOWN,
                    reinforcement_count=1,
                ),
            )
        )
    return entities


def _build_concept_artifacts(
    analysis: dict[str, Any],
    slug: str,
    source_id: str,
    existing_lookup: dict[str, dict[str, str]],
) -> list[ConceptArtifact]:
    concepts: list[ConceptArtifact] = []
    normalized_names: list[str] = []
    for concept_data in analysis.get("concepts", []):
        if isinstance(concept_data, str):
            concept_data = {"name": concept_data, "definition": ""}
        resolved = resolve_existing_name(existing_lookup["concept"], concept_data.get("name", ""))
        normalized_names.append(resolved)
        concept_slug = slugify(resolved)
        concepts.append(
            ConceptArtifact(
                id=artifact_id("concept", concept_slug),
                slug=concept_slug,
                title=resolved,
                definition=concept_data.get("definition", "").strip(),
                source_artifact_ids=[source_id],
                lifecycle=LifecycleMetadata(
                    confidence=0.5,
                    staleness_status=StalenessStatus.UNKNOWN,
                    reinforcement_count=1,
                ),
            )
        )

    if normalized_names:
        related_ids = [artifact_id("concept", slugify(name)) for name in normalized_names]
        for concept in concepts:
            concept.related_concept_ids = [cid for cid in related_ids if cid != concept.id]
    return concepts


def _build_evidence_references(content: SourceContent, source_id: str) -> list[EvidenceReference]:
    excerpt = _collapse_whitespace(content.cleaned_text or content.raw_text)[:400].strip()
    if not excerpt:
        excerpt = (content.source.title or content.source.url).strip()

    return [
        EvidenceReference(
            id=f"{source_id}:evidence:primary",
            source_id=source_id,
            raw_ref=content.raw_capture_kind or "primary_capture",
            excerpt=excerpt,
            confidence=_quality_confidence(content.extraction_quality),
            metadata={
                "source_url": content.source.url,
                "extraction_method": content.extraction_method,
            },
        )
    ]


def _build_relationships(
    *,
    source_id: str,
    topic_artifacts: list[TopicArtifact],
    entity_artifacts: list[EntityArtifact],
    concept_artifacts: list[ConceptArtifact],
    evidence_reference_ids: list[str],
) -> list[RelationshipArtifact]:
    relationships: list[RelationshipArtifact] = []

    for artifact in topic_artifacts:
        relationships.append(
            RelationshipArtifact(
                id=f"{source_id}->topic:{artifact.slug}",
                relationship_type="belongs_to_topic",
                from_artifact_id=source_id,
                to_artifact_id=artifact.id,
                source_artifact_id=source_id,
                evidence_reference_ids=evidence_reference_ids,
            )
        )

    for artifact in entity_artifacts:
        relationships.append(
            RelationshipArtifact(
                id=f"{source_id}->entity:{artifact.slug}",
                relationship_type="mentions_entity",
                from_artifact_id=source_id,
                to_artifact_id=artifact.id,
                source_artifact_id=source_id,
                evidence_reference_ids=evidence_reference_ids,
            )
        )

    for artifact in concept_artifacts:
        relationships.append(
            RelationshipArtifact(
                id=f"{source_id}->concept:{artifact.slug}",
                relationship_type="mentions_concept",
                from_artifact_id=source_id,
                to_artifact_id=artifact.id,
                source_artifact_id=source_id,
                evidence_reference_ids=evidence_reference_ids,
            )
        )

    for topic in topic_artifacts:
        for entity_id in topic.related_entity_ids:
            relationships.append(
                RelationshipArtifact(
                    id=f"{topic.id}->{entity_id}",
                    relationship_type="topic_mentions_entity",
                    from_artifact_id=topic.id,
                    to_artifact_id=entity_id,
                    source_artifact_id=source_id,
                )
            )
        for concept_id in topic.related_concept_ids:
            relationships.append(
                RelationshipArtifact(
                    id=f"{topic.id}->{concept_id}",
                    relationship_type="topic_related_concept",
                    from_artifact_id=topic.id,
                    to_artifact_id=concept_id,
                    source_artifact_id=source_id,
                )
            )

    for entity in entity_artifacts:
        for concept_id in entity.related_concept_ids:
            relationships.append(
                RelationshipArtifact(
                    id=f"{entity.id}->{concept_id}",
                    relationship_type="entity_related_concept",
                    from_artifact_id=entity.id,
                    to_artifact_id=concept_id,
                    source_artifact_id=source_id,
                )
            )

    for concept in concept_artifacts:
        for related_id in concept.related_concept_ids:
            relationships.append(
                RelationshipArtifact(
                    id=f"{concept.id}->{related_id}",
                    relationship_type="concept_related_concept",
                    from_artifact_id=concept.id,
                    to_artifact_id=related_id,
                    source_artifact_id=source_id,
                )
            )

    return relationships


def _clean_list_item(value: str) -> str:
    cleaned = _strip_bullet(value.strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.strip("`")
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    if lowered in {
        "none captured verbatim.",
        "none captured.",
        "none yet.",
        "none yet",
        "summary unavailable.",
    }:
        return ""
    return cleaned


def _strip_bullet(value: str) -> str:
    cleaned = value
    for prefix in _BULLET_PREFIXES:
        if cleaned.startswith(prefix):
            return cleaned[len(prefix) :].strip()
    return re.sub(r"^\d+\.\s+", "", cleaned).strip()


def _collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _quality_confidence(quality: str) -> float:
    return {
        "full": 0.95,
        "mostly_full": 0.8,
        "partial": 0.6,
        "metadata_only": 0.35,
        "failed": 0.1,
    }.get(quality, 0.5)


def _text_value(value: Any) -> str:
    return str(value or "").strip()


def _theme_tags(content: SourceContent, analysis: dict[str, Any]) -> list[str]:
    topic_names = [str(item).strip() for item in analysis.get("topics", []) if str(item).strip()]
    concept_names = []
    for item in analysis.get("concepts", []):
        if isinstance(item, dict):
            name = str(item.get("name", "")).strip()
        else:
            name = str(item).strip()
        if name:
            concept_names.append(name)

    signals = [
        content.source.title or "",
        _text_value(analysis.get("quick_brief")),
        _text_value(analysis.get("summary")),
        " ".join(topic_names),
        " ".join(concept_names),
    ]
    return assign_theme_tags(*signals, source_tags=list(content.source.tags))


def _brief_status(content: SourceContent, analysis: dict[str, Any]) -> str:
    explicit = _text_value(analysis.get("_brief_status")).lower()
    if explicit in {"ready", "partial", "failed"}:
        return explicit

    quality = content.extraction_quality
    if quality == "failed":
        return "failed"
    if quality in {"partial", "metadata_only"}:
        return "partial"
    return "ready"


def _important_terms(analysis: dict[str, Any]) -> list[str]:
    provided = analysis.get("important_terms")
    terms = normalize_markdown_list(provided)
    if terms:
        return terms

    fallback: list[str] = []
    for item in analysis.get("entities", []):
        if isinstance(item, dict):
            name = str(item.get("name", "")).strip()
        else:
            name = str(item).strip()
        if name and name not in fallback:
            fallback.append(name)
    for item in analysis.get("concepts", []):
        if isinstance(item, dict):
            name = str(item.get("name", "")).strip()
        else:
            name = str(item).strip()
        if name and name not in fallback:
            fallback.append(name)
    return fallback[:8]


def _source_lifecycle(content: SourceContent) -> LifecycleMetadata:
    lifecycle = content.lifecycle.model_copy(deep=True)
    if lifecycle.confidence is None:
        lifecycle.confidence = _quality_confidence(content.extraction_quality)
    if not lifecycle.last_confirmed_at:
        lifecycle.last_confirmed_at = content.source.saved_at.isoformat()
    if lifecycle.staleness_status == StalenessStatus.UNKNOWN:
        lifecycle.staleness_status = StalenessStatus.CURRENT
    lifecycle.reinforcement_count = max(1, lifecycle.reinforcement_count)
    return lifecycle
