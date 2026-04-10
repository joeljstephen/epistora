"""Compatibility helpers for current markdown rendering from canonical artifacts."""

from __future__ import annotations

from app.artifacts.builder import render_markdown_list
from app.artifacts.models import (
    ArtifactBundle,
    ConceptArtifact,
    EntityArtifact,
    SynthesisArtifact,
    TopicArtifact,
)
from app.models.knowledge import Concept, Entity, SynthesisNote, Topic


def source_note_payload(bundle: ArtifactBundle) -> dict[str, object]:
    source = bundle.source
    artifacts = bundle.artifact_index()
    topics = [
        artifacts[artifact_id].title
        for artifact_id in source.topic_ids
        if artifact_id in artifacts
    ]
    entities = [
        artifacts[artifact_id].title
        for artifact_id in source.entity_ids
        if artifact_id in artifacts
    ]
    concepts = [
        artifacts[artifact_id].title
        for artifact_id in source.concept_ids
        if artifact_id in artifacts
    ]

    return {
        "summary": source.summary,
        "five_minute_read": source.five_minute_read,
        "detailed_reading_note": source.detailed_note,
        "key_ideas": render_markdown_list(
            source.key_ideas,
            "- No key ideas extracted yet.",
        ),
        "detailed_outline": source.detailed_outline or "## Coverage\n- Outline unavailable.",
        "important_examples": render_markdown_list(
            source.examples,
            "- No concrete examples captured.",
        ),
        "actionable_takeaways": render_markdown_list(
            source.takeaways,
            "- No actionable takeaways extracted.",
        ),
        "notable_quotes": render_markdown_list(
            source.quotes,
            "- None captured verbatim.",
        ),
        "best_for": render_markdown_list(
            source.best_for,
            "- General manual review.",
        ),
        "consume_recommendation": source.consume_recommendation,
        "why_it_matters": source.why_it_matters,
        "open_questions": render_markdown_list(
            source.open_questions,
            "- What is still missing from this capture?",
        ),
        "topics": topics,
        "entities": entities,
        "concepts": concepts,
    }


def legacy_topic(topic: TopicArtifact, *, bundle: ArtifactBundle) -> Topic:
    artifacts = bundle.artifact_index()
    related_concepts = [
        artifacts[artifact_id].title
        for artifact_id in topic.related_concept_ids
        if artifact_id in artifacts
    ]
    related_entities = [
        artifacts[artifact_id].title
        for artifact_id in topic.related_entity_ids
        if artifact_id in artifacts
    ]
    return Topic(
        name=topic.title,
        slug=topic.slug,
        summary=topic.summary,
        source_ids=list(topic.source_artifact_ids),
        related_concepts=related_concepts,
        related_entities=related_entities,
        lifecycle=topic.lifecycle,
    )


def legacy_entity(entity: EntityArtifact, *, bundle: ArtifactBundle) -> Entity:
    artifacts = bundle.artifact_index()
    related_concepts = [
        artifacts[artifact_id].title
        for artifact_id in entity.related_concept_ids
        if artifact_id in artifacts
    ]
    return Entity(
        name=entity.title,
        slug=entity.slug,
        entity_type=entity.entity_type,
        description=entity.summary,
        source_ids=list(entity.source_artifact_ids),
        related_concepts=related_concepts,
        lifecycle=entity.lifecycle,
    )


def legacy_concept(concept: ConceptArtifact, *, bundle: ArtifactBundle) -> Concept:
    artifacts = bundle.artifact_index()
    related_concepts = [
        artifacts[artifact_id].title
        for artifact_id in concept.related_concept_ids
        if artifact_id in artifacts
    ]
    return Concept(
        name=concept.title,
        slug=concept.slug,
        definition=concept.definition,
        source_ids=list(concept.source_artifact_ids),
        related_concepts=related_concepts,
        lifecycle=concept.lifecycle,
    )


def legacy_synthesis(note: SynthesisArtifact) -> SynthesisNote:
    return SynthesisNote(
        title=note.title,
        slug=note.slug,
        summary=note.summary,
        source_basis=list(note.source_basis_ids),
        main_patterns=render_markdown_list(note.patterns, "_No patterns captured yet._"),
        conflicts=render_markdown_list(note.disagreements, "_No disagreements captured yet._"),
        next_steps=render_markdown_list(
            note.reusable_takeaways,
            "_No reusable takeaways captured yet._",
        ),
        lifecycle=note.lifecycle,
    )
