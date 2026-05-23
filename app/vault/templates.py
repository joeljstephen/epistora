"""Markdown note templates for all vault note types."""

from __future__ import annotations

from app.artifacts.models import (
    ConceptArtifact,
    EntityArtifact,
    SynthesisArtifact,
    TopicArtifact,
)
from app.models.knowledge import Concept, Entity, SynthesisNote, Topic
from app.models.source import SourceContent
from app.utils.dates import friendly_date
from app.utils.markdown import build_frontmatter_doc, path_wikilink, wikilink


def source_note_md(
    content: SourceContent,
    raw_capture_path: str,
    quick_brief: str,
    summary: str,
    five_minute_read: str,
    detailed_reading_note: str,
    best_next_action: str,
    theme_tags: list[str],
    brief_status: str,
    watch_verdict: str,
    watch_verdict_reasoning: str,
    quick_section_guide: str,
    detailed_sections: str,
    signal_vs_filler: str,
    important_terms: str,
    key_ideas: str,
    detailed_outline: str,
    important_examples: str,
    actionable_takeaways: str,
    notable_quotes: str,
    best_for: str,
    consume_recommendation: str,
    why_it_matters: str,
    open_questions: str,
    topics: list[str],
    entities: list[str],
    concepts: list[str],
    user_state: dict[str, object] | None = None,
) -> str:
    source_title = content.source.title or content.source.url
    raw_blob_path = str(content.raw_metadata.get("blob_path", "") or "")
    user_state = dict(user_state or {})
    reading_state = _resolved_reading_state(
        content=content,
        brief_status=brief_status,
        best_next_action=best_next_action,
        watch_verdict=watch_verdict,
        user_state=user_state,
    )
    channel_or_author = (
        content.author
        or str(content.raw_metadata.get("channel", "") or "").strip()
        or str(content.raw_metadata.get("site_name", "") or "").strip()
    )
    cover_image = (
        str(content.raw_metadata.get("thumbnail_url", "") or "").strip()
        or str(content.raw_metadata.get("image_url", "") or "").strip()
    )
    meta = {
        "title": source_title,
        "type": "source",
        "source_url": content.source.url,
        "source_type": content.source.source_type.value,
        "author": content.author,
        "published_date": content.published_date,
        "saved_at": content.source.saved_at.isoformat(timespec="seconds"),
        "ingested_at": friendly_date(),
        "tags": content.source.tags,
        "theme_tags": theme_tags,
        "brief_status": brief_status,
        "reading_state": reading_state,
        "quick_summary": quick_brief or summary,
        "best_next_action": best_next_action,
        "why_it_matters": why_it_matters,
        "channel_or_author": channel_or_author,
        "consume_recommendation": consume_recommendation,
        "topics": topics,
        "entities": entities,
        "concepts": concepts,
        "word_count": content.word_count,
        "extraction_quality": content.extraction_quality,
        "extraction_method": content.extraction_method,
        "extraction_fallback_chain": content.extraction_fallback_chain,
        "raw_capture_path": raw_capture_path,
        "raw_capture_kind": content.raw_capture_kind,
        "lifecycle": content.lifecycle.as_frontmatter(),
    }
    if user_state:
        meta["user_state"] = user_state
    if watch_verdict:
        meta["watch_verdict"] = watch_verdict
    if important_terms.strip():
        meta["important_terms"] = [
            line.removeprefix("- ").strip()
            for line in important_terms.splitlines()
            if line.strip().startswith("- ")
        ]
    if cover_image:
        meta["cover_image"] = cover_image
    meta.update(_source_frontmatter_extras(content))
    if content.canonical_url and content.canonical_url != content.source.url:
        meta["canonical_url"] = content.canonical_url

    topic_links = ", ".join(wikilink(topic) for topic in topics) if topics else "_None yet_"
    entity_links = (
        ", ".join(wikilink(entity) for entity in entities) if entities else "_None yet_"
    )
    concept_links = (
        ", ".join(wikilink(concept) for concept in concepts) if concepts else "_None yet_"
    )
    raw_link = path_wikilink(raw_capture_path, "Raw archive") if raw_capture_path else "_Missing_"
    blob_link = path_wikilink(raw_blob_path, "Full blob evidence") if raw_blob_path else ""
    tags = ", ".join(content.source.tags) if content.source.tags else "_None_"

    header_lines = [
        f"# {source_title}",
        "",
        f"> **Source:** {content.source.url}",
        f"> **Type:** {content.source.source_type.value}",
        f"> **Ingested:** {friendly_date()}",
        (
            f"> **Evidence quality:** `{content.extraction_quality}` via "
            f"`{content.extraction_method or 'unknown'}`"
        ),
        f"> **Raw archive:** {raw_link}",
    ]
    if blob_link:
        header_lines.append(f"> **Full blob evidence:** {blob_link}")
    header_lines.extend(
        [
            f"> **Saved tags:** {tags}",
            "",
            _source_specific_body(
                content=content,
                quick_brief=quick_brief,
                summary=summary,
                five_minute_read=five_minute_read,
                detailed_reading_note=detailed_reading_note,
                best_next_action=best_next_action,
                watch_verdict=watch_verdict,
                watch_verdict_reasoning=watch_verdict_reasoning,
                quick_section_guide=quick_section_guide,
                detailed_sections=detailed_sections,
                signal_vs_filler=signal_vs_filler,
                important_terms=important_terms,
                key_ideas=key_ideas,
                detailed_outline=detailed_outline,
                important_examples=important_examples,
                actionable_takeaways=actionable_takeaways,
                notable_quotes=notable_quotes,
                best_for=best_for,
                consume_recommendation=consume_recommendation,
                why_it_matters=why_it_matters,
                open_questions=open_questions,
                topic_links=topic_links,
                entity_links=entity_links,
                concept_links=concept_links,
            ),
        ]
    )

    body = "\n".join(header_lines).strip()

    return build_frontmatter_doc(meta, body)


def _source_specific_body(
    *,
    content: SourceContent,
    quick_brief: str,
    summary: str,
    five_minute_read: str,
    detailed_reading_note: str,
    best_next_action: str,
    watch_verdict: str,
    watch_verdict_reasoning: str,
    quick_section_guide: str,
    detailed_sections: str,
    signal_vs_filler: str,
    important_terms: str,
    key_ideas: str,
    detailed_outline: str,
    important_examples: str,
    actionable_takeaways: str,
    notable_quotes: str,
    best_for: str,
    consume_recommendation: str,
    why_it_matters: str,
    open_questions: str,
    topic_links: str,
    entity_links: str,
    concept_links: str,
) -> str:
    common_sections = [
        "## Coverage & Limits\n\n" + _coverage_and_limits_md(content),
        "## Why This Matters\n\n" + why_it_matters,
        "## Related Notes\n\n"
        + "\n".join(
            [
                f"- **Topics:** {topic_links}",
                f"- **Entities:** {entity_links}",
                f"- **Concepts:** {concept_links}",
            ]
        ),
        "## Important Examples\n\n" + important_examples,
        "## Detailed Outline\n\n" + detailed_outline,
        "## Key Ideas\n\n" + key_ideas,
        "## Actionable Takeaways\n\n" + actionable_takeaways,
        "## Notable Quotes\n\n" + notable_quotes,
        "## Who This Is Useful For\n\n" + best_for,
        "## Open Questions\n\n" + open_questions,
        "## Capture Notes\n\n" + _capture_notes_md(content),
    ]

    if content.source.source_type.value == "youtube":
        sections = [
            "## Overview\n\n" + (quick_brief or summary),
            "## Quick Section Guide\n\n"
            + (quick_section_guide or five_minute_read or "_Section guide unavailable._"),
            "## Should I Watch This?\n\n"
            + _youtube_watch_block(
                watch_verdict=watch_verdict,
                watch_verdict_reasoning=watch_verdict_reasoning,
                best_next_action=best_next_action,
                consume_recommendation=consume_recommendation,
            ),
            "## Detailed Section-by-Section Breakdown\n\n"
            + (detailed_sections or detailed_reading_note),
            "## Key Takeaways\n\n" + actionable_takeaways,
            "## Important Terms / People / Tools\n\n" + important_terms,
            "## Signal vs Filler\n\n"
            + (signal_vs_filler or _default_signal_vs_filler_md(content)),
            "## Evidence / Transcript Status\n\n" + _youtube_transcript_status(content),
        ]
        sections.extend(common_sections)
        return "\n\n".join(sections)

    if content.source.source_type.value == "article":
        sections = [
            "## Overview\n\n" + (quick_brief or summary),
            "## Best Next Action\n\n" + (best_next_action or consume_recommendation),
            "## Should I Still Read The Original?\n\n" + consume_recommendation,
            "## 5-Minute Read\n\n" + five_minute_read,
            "## Detailed Reading Note\n\n" + detailed_reading_note,
        ]
        sections.extend(common_sections)
        return "\n\n".join(sections)

    sections = [
        "## Overview\n\n" + (quick_brief or summary),
        "## Best Next Action\n\n" + (best_next_action or consume_recommendation),
        "## 5-Minute Read\n\n" + five_minute_read,
        "## Detailed Reading Note\n\n" + detailed_reading_note,
        "## Should I Still Consult The Original?\n\n" + consume_recommendation,
    ]
    sections.extend(common_sections)
    return "\n\n".join(sections)


def _youtube_watch_block(
    *,
    watch_verdict: str,
    watch_verdict_reasoning: str,
    best_next_action: str,
    consume_recommendation: str,
) -> str:
    verdict = watch_verdict or "Open the original only if the topic becomes active."
    reasoning = watch_verdict_reasoning or consume_recommendation
    action = best_next_action or consume_recommendation
    return "\n".join(
        [
            f"- **Verdict:** {verdict}",
            f"- **Why:** {reasoning}",
            f"- **Best next action:** {action}",
        ]
    )


def _default_signal_vs_filler_md(content: SourceContent) -> str:
    if content.extraction_quality in {"partial", "metadata_only", "failed"}:
        return (
            "- Signal estimate is limited because the capture was incomplete.\n"
            "- Use the raw archive when exact structure or supporting details matter."
        )
    return (
        "- The captured brief preserves the likely high-signal points.\n"
        "- Use the raw archive or original source if presentation, tone, or missing context matter."
    )


def _resolved_reading_state(
    *,
    content: SourceContent,
    brief_status: str,
    best_next_action: str,
    watch_verdict: str,
    user_state: dict[str, object],
) -> str:
    override = str(user_state.get("reading_state", "") or "").strip()
    if override:
        return override

    guidance = " ".join(part for part in (best_next_action, watch_verdict) if part).lower()
    if any(token in guidance for token in ("skip", "deprioritize", "brief may be enough")):
        return "brief_may_be_enough"
    if brief_status == "partial":
        return "queued"
    if content.source.source_type.value == "youtube" and "watch" in guidance:
        return "up_next"
    return "up_next"


def _youtube_transcript_status(content: SourceContent) -> str:
    transcript_available = bool(content.raw_metadata.get("transcript_available"))
    caption_type = content.raw_metadata.get("caption_type", "none")
    source = content.raw_metadata.get("transcript_source", content.extraction_method or "unknown")
    channel = content.author or content.raw_metadata.get("channel", "")
    duration = content.raw_metadata.get("duration", "")
    transcript_quality = content.raw_metadata.get("transcript_quality", "")
    section_count = content.raw_metadata.get("transcript_section_count", "")

    lines = [
        f"- Transcript available: {'yes' if transcript_available else 'no'}",
        f"- Caption type: {caption_type}",
        f"- Extraction source: {source}",
    ]
    if transcript_quality:
        lines.append(f"- Transcript quality: {transcript_quality}")
    if section_count:
        lines.append(f"- Structured sections captured: {section_count}")
    if channel:
        lines.append(f"- Channel: {channel}")
    if duration:
        lines.append(f"- Duration: {duration}")
    return "\n".join(lines)


def _capture_notes_md(content: SourceContent) -> str:
    lines = [
        f"- Extraction quality: `{content.extraction_quality}`",
        f"- Extraction method: `{content.extraction_method or 'unknown'}`",
    ]
    if content.raw_metadata.get("storage_tier"):
        lines.append(f"- Raw storage tier: `{content.raw_metadata['storage_tier']}`")
    if content.raw_metadata.get("blob_storage_tier"):
        lines.append(f"- Blob storage tier: `{content.raw_metadata['blob_storage_tier']}`")
    if content.raw_metadata.get("blob_path"):
        lines.append(f"- Full blob path: {content.raw_metadata['blob_path']}")
    if content.raw_metadata.get("blob_bytes"):
        lines.append(f"- Blob size: `{content.raw_metadata['blob_bytes']}` bytes")
    if content.raw_metadata.get("blob_sha256"):
        lines.append(f"- Blob SHA-256: `{content.raw_metadata['blob_sha256']}`")
    if content.extraction_fallback_chain:
        lines.append(
            "- Fallback chain: "
            + " -> ".join(f"`{step}`" for step in content.extraction_fallback_chain)
        )
    if content.canonical_url and content.canonical_url != content.source.url:
        lines.append(f"- Canonical URL: {content.canonical_url}")
    if content.extraction_notes:
        lines.append(f"- Notes: {content.extraction_notes}")
    return "\n".join(lines)


def _coverage_and_limits_md(content: SourceContent) -> str:
    lines = [
        f"- Raw evidence kind: `{content.raw_capture_kind or 'unknown'}`",
        f"- Extraction quality: `{content.extraction_quality}`",
    ]
    if content.raw_metadata.get("blob_path"):
        lines.append("- Full preserved evidence is blob-backed under `.system/blobs/`.")
    else:
        lines.append("- Full preserved evidence remains directly readable in `raw/`.")

    if content.source.source_type.value == "article":
        archived = bool(content.raw_metadata.get("article_archive_available"))
        lines.append(f"- Readable article archive preserved: {'yes' if archived else 'no'}")
    elif content.source.source_type.value == "youtube":
        lines.append(
            "- Transcript captured: "
            + ("yes" if content.raw_metadata.get("transcript_available") else "no")
        )

    if content.extraction_quality in {"metadata_only", "partial", "failed"}:
        lines.append(
            "- Limitation: this note should be read as a partial compilation, "
            "not a complete capture."
        )
    else:
        lines.append(
            "- Coverage: the vault captured enough evidence for a substantive "
            "compiled note."
        )

    return "\n".join(lines)


def _source_frontmatter_extras(content: SourceContent) -> dict[str, object]:
    extra: dict[str, object] = {
        "archive_separation": "raw_evidence_and_compiled_note",
        "raw_storage_tier": content.raw_metadata.get("storage_tier", "warm"),
    }
    if content.derived_work_kind or content.source.derived_work_kind:
        extra["derived_work_kind"] = content.derived_work_kind or content.source.derived_work_kind
    if content.raw_metadata.get("blob_path"):
        extra["raw_blob_path"] = content.raw_metadata.get("blob_path")
    if content.raw_metadata.get("blob_storage_tier"):
        extra["raw_blob_storage_tier"] = content.raw_metadata.get("blob_storage_tier")
    if content.raw_metadata.get("blob_bytes"):
        extra["raw_blob_bytes"] = content.raw_metadata.get("blob_bytes")
    if content.raw_metadata.get("blob_sha256"):
        extra["raw_blob_sha256"] = content.raw_metadata.get("blob_sha256")

    if content.source.source_type.value == "youtube":
        extra["transcript_available"] = bool(content.raw_metadata.get("transcript_available"))
        if content.raw_metadata.get("caption_type"):
            extra["caption_type"] = content.raw_metadata.get("caption_type")
        if content.raw_metadata.get("transcript_quality"):
            extra["transcript_quality"] = content.raw_metadata.get("transcript_quality")
    if content.source.source_type.value == "article":
        extra["article_archive_available"] = bool(
            content.raw_metadata.get("article_archive_available")
        )

    return extra


def topic_note_md(
    topic: Topic,
    source_titles: list[str],
    sections: dict[str, str] | None = None,
) -> str:
    sections = sections or {}
    topic_summary = topic.summary or "_This topic page will strengthen as more sources accumulate._"
    recurring_patterns = "_Patterns will be written here as repeated ideas emerge across sources._"
    conflicting_viewpoints = "_Record disagreements, tensions, or unresolved tradeoffs here._"
    suggested_next = "_Add likely next sources or questions to pursue._"
    meta = {
        "title": topic.name,
        "type": "topic",
        "slug": topic.slug,
        "updated_at": friendly_date(),
        "lifecycle": topic.lifecycle.as_frontmatter(),
    }

    source_list = (
        "\n".join(f"- {wikilink(title)}" for title in source_titles)
        if source_titles
        else "- _No sources yet_"
    )
    concept_links = (
        ", ".join(wikilink(concept) for concept in topic.related_concepts)
        if topic.related_concepts
        else "_None yet_"
    )
    entity_links = (
        ", ".join(wikilink(entity) for entity in topic.related_entities)
        if topic.related_entities
        else "_None yet_"
    )

    body = f"""# {topic.name}

## Topic Summary

{sections.get("Topic Summary", topic_summary)}

## What I Have Saved

{source_list}

## Related Concepts

{sections.get("Related Concepts", concept_links)}

## Important Entities

{sections.get("Important Entities", entity_links)}

## Recurring Patterns

{sections.get("Recurring Patterns", recurring_patterns)}

## Conflicting Viewpoints

{sections.get("Conflicting Viewpoints", conflicting_viewpoints)}

## Gaps In My Understanding

{sections.get("Gaps In My Understanding", "_Identify what still feels thin or under-explained._")}

## Active Questions

{sections.get(
    "Active Questions",
    "_Record live questions that should shape future ingest or synthesis._",
)}

## Suggested Next Reading / Watching

{sections.get("Suggested Next Reading / Watching", suggested_next)}
"""
    return build_frontmatter_doc(meta, body)


def topic_artifact_note_md(
    topic: TopicArtifact,
    source_titles: list[str],
    *,
    related_concepts: list[str] | None = None,
    related_entities: list[str] | None = None,
    sections: dict[str, str] | None = None,
) -> str:
    sections = sections or {}
    related_concepts = related_concepts or []
    related_entities = related_entities or []
    topic_summary = topic.summary or "_This topic page will strengthen as more sources accumulate._"
    recurring_patterns = (
        "\n".join(f"- {pattern}" for pattern in topic.patterns)
        if topic.patterns
        else "_Patterns will be written here as repeated ideas emerge across sources._"
    )
    conflicting_viewpoints = (
        "\n".join(f"- {conflict}" for conflict in topic.conflicts)
        if topic.conflicts
        else "_Record disagreements, tensions, or unresolved tradeoffs here._"
    )
    gaps = (
        "\n".join(f"- {gap}" for gap in topic.gaps)
        if topic.gaps
        else "_Identify what still feels thin or under-explained._"
    )
    suggested_next = "_Add likely next sources or questions to pursue._"
    meta = {
        "title": topic.title,
        "type": "topic",
        "slug": topic.slug,
        "updated_at": friendly_date(),
        "lifecycle": topic.lifecycle.as_frontmatter(),
    }

    source_list = (
        "\n".join(f"- {wikilink(title)}" for title in source_titles)
        if source_titles
        else "- _No sources yet_"
    )
    concept_links = (
        ", ".join(wikilink(concept) for concept in related_concepts)
        if related_concepts
        else "_None yet_"
    )
    entity_links = (
        ", ".join(wikilink(entity) for entity in related_entities)
        if related_entities
        else "_None yet_"
    )

    body = f"""# {topic.title}

## Topic Summary

{sections.get("Topic Summary", topic_summary)}

## What I Have Saved

{source_list}

## Related Concepts

{sections.get("Related Concepts", concept_links)}

## Important Entities

{sections.get("Important Entities", entity_links)}

## Recurring Patterns

{sections.get("Recurring Patterns", recurring_patterns)}

## Conflicting Viewpoints

{sections.get("Conflicting Viewpoints", conflicting_viewpoints)}

## Gaps In My Understanding

{sections.get("Gaps In My Understanding", gaps)}

## Active Questions

{sections.get(
    "Active Questions",
    "_Record live questions that should shape future ingest or synthesis._",
)}

## Suggested Next Reading / Watching

{sections.get("Suggested Next Reading / Watching", suggested_next)}
"""
    return build_frontmatter_doc(meta, body)


def entity_note_md(
    entity: Entity,
    source_titles: list[str],
    sections: dict[str, str] | None = None,
) -> str:
    sections = sections or {}
    what_it_is = (
        entity.description or f"_{entity.entity_type.title()} referenced in saved sources._"
    )
    why_it_shows_up = f"Referenced in {len(source_titles)} source(s) in this vault."
    recurring_contexts = "_Capture the recurring roles or contexts this entity appears in._"
    why_it_matters = "_State why this entity matters to the wider wiki, not just this source._"
    open_questions = "_Track ambiguities, missing details, or follow-up questions here._"
    meta = {
        "title": entity.name,
        "type": "entity",
        "entity_type": entity.entity_type,
        "slug": entity.slug,
        "updated_at": friendly_date(),
        "lifecycle": entity.lifecycle.as_frontmatter(),
    }

    mentions = (
        "\n".join(f"- {wikilink(title)}" for title in source_titles)
        if source_titles
        else "- _No mentions yet_"
    )
    concept_links = (
        ", ".join(wikilink(concept) for concept in entity.related_concepts)
        if entity.related_concepts
        else "_None yet_"
    )

    body = f"""# {entity.name}

## What It Is

{sections.get("What It Is", what_it_is)}

## Why It Shows Up In My Vault

{sections.get("Why It Shows Up In My Vault", why_it_shows_up)}

## Recurring Contexts

{sections.get("Recurring Contexts", recurring_contexts)}

## Why It Matters

{sections.get("Why It Matters", why_it_matters)}

## Related Concepts

{sections.get("Related Concepts", concept_links)}

## Mentioned In

{mentions}

## Open Questions

{sections.get("Open Questions", open_questions)}
"""
    return build_frontmatter_doc(meta, body)


def entity_artifact_note_md(
    entity: EntityArtifact,
    source_titles: list[str],
    *,
    related_concepts: list[str] | None = None,
    sections: dict[str, str] | None = None,
) -> str:
    sections = sections or {}
    related_concepts = related_concepts or []
    what_it_is = entity.summary or f"_{entity.entity_type.title()} referenced in saved sources._"
    why_it_shows_up = f"Referenced in {len(source_titles)} source(s) in this vault."
    recurring_contexts = (
        "\n".join(f"- {context}" for context in entity.contexts)
        if entity.contexts
        else "_Capture the recurring roles or contexts this entity appears in._"
    )
    why_it_matters = "_State why this entity matters to the wider wiki, not just this source._"
    open_questions = "_Track ambiguities, missing details, or follow-up questions here._"
    meta = {
        "title": entity.title,
        "type": "entity",
        "entity_type": entity.entity_type,
        "slug": entity.slug,
        "updated_at": friendly_date(),
        "lifecycle": entity.lifecycle.as_frontmatter(),
    }

    mentions = (
        "\n".join(f"- {wikilink(title)}" for title in source_titles)
        if source_titles
        else "- _No mentions yet_"
    )
    concept_links = (
        ", ".join(wikilink(concept) for concept in related_concepts)
        if related_concepts
        else "_None yet_"
    )

    body = f"""# {entity.title}

## What It Is

{sections.get("What It Is", what_it_is)}

## Why It Shows Up In My Vault

{sections.get("Why It Shows Up In My Vault", why_it_shows_up)}

## Recurring Contexts

{sections.get("Recurring Contexts", recurring_contexts)}

## Why It Matters

{sections.get("Why It Matters", why_it_matters)}

## Related Concepts

{sections.get("Related Concepts", concept_links)}

## Mentioned In

{mentions}

## Open Questions

{sections.get("Open Questions", open_questions)}
"""
    return build_frontmatter_doc(meta, body)


def concept_note_md(
    concept: Concept,
    source_titles: list[str],
    sections: dict[str, str] | None = None,
) -> str:
    sections = sections or {}
    definition = (
        concept.definition or "_Definition will be refined as more sources mention this concept._"
    )
    open_questions = "_Track unclear edges, competing definitions, or missing examples._"
    meta = {
        "title": concept.name,
        "type": "concept",
        "slug": concept.slug,
        "updated_at": friendly_date(),
        "lifecycle": concept.lifecycle.as_frontmatter(),
    }

    sources = (
        "\n".join(f"- {wikilink(title)}" for title in source_titles)
        if source_titles
        else "- _No examples yet_"
    )
    related = (
        ", ".join(wikilink(item) for item in concept.related_concepts)
        if concept.related_concepts
        else "_None yet_"
    )

    body = f"""# {concept.name}

## Definition

{sections.get("Definition", definition)}

## Why It Matters

{sections.get("Why It Matters", "_Explain why this concept keeps showing up in the vault._")}

## Where It Appears

{sources}

## Related Concepts

{sections.get("Related Concepts", related)}

## Examples From Saved Sources

{sections.get("Examples From Saved Sources", "_Examples will be extracted as the vault grows._")}

## Competing Definitions / Edge Cases

{sections.get(
    "Competing Definitions / Edge Cases",
    "_Capture disagreements, boundary cases, or overloaded meanings here._",
)}

## Open Questions

{sections.get("Open Questions", open_questions)}
"""
    return build_frontmatter_doc(meta, body)


def concept_artifact_note_md(
    concept: ConceptArtifact,
    source_titles: list[str],
    *,
    related_concepts: list[str] | None = None,
    sections: dict[str, str] | None = None,
) -> str:
    sections = sections or {}
    related_concepts = related_concepts or []
    definition = (
        concept.definition or "_Definition will be refined as more sources mention this concept._"
    )
    examples = (
        "\n".join(f"- {example}" for example in concept.examples)
        if concept.examples
        else "_Examples will be extracted as the vault grows._"
    )
    gaps = (
        "\n".join(f"- {gap}" for gap in concept.gaps)
        if concept.gaps
        else "_Capture disagreements, boundary cases, or overloaded meanings here._"
    )
    open_questions = "_Track unclear edges, competing definitions, or missing examples._"
    meta = {
        "title": concept.title,
        "type": "concept",
        "slug": concept.slug,
        "updated_at": friendly_date(),
        "lifecycle": concept.lifecycle.as_frontmatter(),
    }

    sources = (
        "\n".join(f"- {wikilink(title)}" for title in source_titles)
        if source_titles
        else "- _No examples yet_"
    )
    related = (
        ", ".join(wikilink(item) for item in related_concepts)
        if related_concepts
        else "_None yet_"
    )

    body = f"""# {concept.title}

## Definition

{sections.get("Definition", definition)}

## Why It Matters

{sections.get("Why It Matters", "_Explain why this concept keeps showing up in the vault._")}

## Where It Appears

{sources}

## Related Concepts

{sections.get("Related Concepts", related)}

## Examples From Saved Sources

{sections.get("Examples From Saved Sources", examples)}

## Competing Definitions / Edge Cases

{sections.get("Competing Definitions / Edge Cases", gaps)}

## Open Questions

{sections.get("Open Questions", open_questions)}
"""
    return build_frontmatter_doc(meta, body)


def synthesis_note_md(note: SynthesisNote) -> str:
    meta = {
        "title": note.title,
        "type": "synthesis",
        "slug": note.slug,
        "created_at": friendly_date(note.created_at),
        "lifecycle": note.lifecycle.as_frontmatter(),
    }

    basis = (
        "\n".join(f"- {wikilink(source)}" for source in note.source_basis)
        if note.source_basis
        else "- _No sources_"
    )

    body = f"""# {note.title}

## Durable Claim

{note.summary}

## Source Basis

{basis}

## Cross-Source Patterns

{note.main_patterns or "_No patterns identified yet._"}

## Conflicts Or Tensions

{note.conflicts or "_No conflicts detected._"}

## Reusable Takeaways / Next Moves

{note.next_steps or "_No reusable takeaways recorded yet._"}
"""
    return build_frontmatter_doc(meta, body)


def synthesis_artifact_note_md(note: SynthesisArtifact) -> str:
    meta = {
        "title": note.title,
        "type": "synthesis",
        "slug": note.slug,
        "created_at": friendly_date(),
        "lifecycle": note.lifecycle.as_frontmatter(),
    }

    basis = (
        "\n".join(f"- {wikilink(source_id)}" for source_id in note.source_basis_ids)
        if note.source_basis_ids
        else "- _No sources_"
    )
    patterns = (
        "\n".join(f"- {pattern}" for pattern in note.patterns)
        if note.patterns
        else "_No patterns identified yet._"
    )
    disagreements = (
        "\n".join(f"- {disagreement}" for disagreement in note.disagreements)
        if note.disagreements
        else "_No conflicts detected._"
    )
    reusable_takeaways = (
        "\n".join(f"- {takeaway}" for takeaway in note.reusable_takeaways)
        if note.reusable_takeaways
        else "_No reusable takeaways recorded yet._"
    )

    body = f"""# {note.title}

## Durable Claim

{note.summary}

## Source Basis

{basis}

## Cross-Source Patterns

{patterns}

## Conflicts Or Tensions

{disagreements}

## Reusable Takeaways / Next Moves

{reusable_takeaways}
"""
    return build_frontmatter_doc(meta, body)


def raw_capture_md(content: SourceContent) -> str:
    source_title = content.source.title or content.source.url
    blob_path = str(content.raw_metadata.get("blob_path", "") or "")
    meta = {
        "title": source_title,
        "type": "raw",
        "source_url": content.source.url,
        "source_type": content.source.source_type.value,
        "captured_at": friendly_date(),
        "immutable": True,
        "raw_capture_kind": content.raw_capture_kind,
        "extraction_quality": content.extraction_quality,
        "extraction_method": content.extraction_method,
        "storage_tier": content.raw_metadata.get("storage_tier", "warm"),
    }
    if blob_path:
        meta["blob_path"] = blob_path
    if content.raw_metadata.get("blob_storage_tier"):
        meta["blob_storage_tier"] = content.raw_metadata.get("blob_storage_tier")
    if content.raw_metadata.get("blob_bytes"):
        meta["blob_bytes"] = content.raw_metadata.get("blob_bytes")
    if content.raw_metadata.get("blob_sha256"):
        meta["blob_sha256"] = content.raw_metadata.get("blob_sha256")
    if content.raw_metadata.get("blob_media_type"):
        meta["blob_media_type"] = content.raw_metadata.get("blob_media_type")
    if content.raw_metadata.get("raw_preview_chars"):
        meta["raw_preview_chars"] = content.raw_metadata.get("raw_preview_chars")
    if content.canonical_url and content.canonical_url != content.source.url:
        meta["canonical_url"] = content.canonical_url

    if blob_path:
        blob_link = path_wikilink(blob_path, "Full preserved evidence blob")
        preview = str(content.raw_metadata.get("raw_preview_text", "") or "").strip()
        if not preview:
            preview = "_No readable preview available._"
        body = f"""# {source_title}

> Immutable raw capture generated by Epistora.
> Source: {content.source.url}
> Extraction: {content.extraction_method or 'unknown'} ({content.extraction_quality})
> Storage tiers: warm manifest note + cold blob
> Full evidence blob: {blob_link}
> Blob size: {content.raw_metadata.get("blob_bytes", "unknown")} bytes
> Blob SHA-256: {content.raw_metadata.get("blob_sha256", "unknown")}

## Preview

{preview}

## Storage Notes

- This raw note remains the stable visible reference in the vault.
- The full evidence payload is preserved in the blob path above to keep the hot
  working layer readable.
"""
    elif content.archived_markdown.strip():
        body = content.archived_markdown.strip()
    else:
        body = f"""# {source_title}

> Immutable raw capture generated by Epistora.
> Source: {content.source.url}
> Extraction: {content.extraction_method or 'unknown'} ({content.extraction_quality})

{content.raw_text or content.cleaned_text or "_No raw text captured._"}
"""

    return build_frontmatter_doc(meta, body)
