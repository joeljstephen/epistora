"""Vault-facing payload helpers for canonical Artifact Bundles."""

from __future__ import annotations

from app.artifacts.builder import render_markdown_list
from app.artifacts.models import ArtifactBundle


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
        "quick_brief": source.quick_brief or source.summary,
        "summary": source.summary,
        "five_minute_read": source.five_minute_read,
        "detailed_reading_note": source.detailed_note,
        "best_next_action": source.best_next_action or source.consume_recommendation,
        "theme_tags": list(source.theme_tags),
        "brief_status": source.brief_status or "partial",
        "watch_verdict": source.watch_verdict,
        "watch_verdict_reasoning": source.watch_verdict_reasoning,
        "quick_section_guide": source.quick_section_guide,
        "detailed_sections": source.detailed_sections,
        "signal_vs_filler": source.signal_vs_filler,
        "important_terms": render_markdown_list(
            source.important_terms,
            "- No especially important terms identified yet.",
        ),
        "key_ideas": render_markdown_list(
            source.key_ideas,
            "- No key ideas extracted yet.",
        ),
        "detailed_outline": source.detailed_outline or "## Coverage\n- Outline unavailable.",
        "important_examples": render_markdown_list(
            source.examples,
            "- No concrete examples captured.",
        ),
        "takeaways": render_markdown_list(
            source.takeaways,
            "- No takeaways extracted.",
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
