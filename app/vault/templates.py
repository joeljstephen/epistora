"""Markdown note templates for all vault note types."""

from __future__ import annotations

from app.models.knowledge import Concept, Entity, SynthesisNote, Topic
from app.models.source import SourceContent
from app.utils.dates import friendly_date
from app.utils.markdown import build_frontmatter_doc, wikilink


def source_note_md(
    content: SourceContent,
    summary: str,
    key_takeaways: str,
    detailed_outline: str,
    important_claims: str,
    why_matters: str,
    open_questions: str,
    topics: list[str],
    entities: list[str],
    concepts: list[str],
) -> str:
    meta = {
        "title": content.source.title,
        "type": "source",
        "source_url": content.source.url,
        "source_type": content.source.source_type.value,
        "author": content.author,
        "published_date": content.published_date,
        "ingested_at": friendly_date(),
        "tags": content.source.tags,
        "topics": topics,
        "entities": entities,
        "concepts": concepts,
        "word_count": content.word_count,
        "extraction_quality": content.extraction_quality,
    }

    topic_links = ", ".join(wikilink(t) for t in topics) if topics else "_None yet_"
    entity_links = ", ".join(wikilink(e) for e in entities) if entities else "_None yet_"
    concept_links = ", ".join(wikilink(c) for c in concepts) if concepts else "_None yet_"

    body = f"""# {content.source.title}

> **Source:** {content.source.url}
> **Type:** {content.source.source_type.value} | **Ingested:** {friendly_date()}

## Summary

{summary}

## Key Takeaways

{key_takeaways}

## Detailed Outline

{detailed_outline}

## Important Claims

{important_claims}

## Why This Matters

{why_matters}

## Open Questions

{open_questions}

## Related Notes

- **Topics:** {topic_links}
- **Entities:** {entity_links}
- **Concepts:** {concept_links}
"""
    if content.extraction_notes:
        body += f"\n---\n\n> **Extraction note:** {content.extraction_notes}\n"

    return build_frontmatter_doc(meta, body)


def topic_note_md(
    topic: Topic,
    source_titles: list[str],
    sections: dict[str, str] | None = None,
) -> str:
    sections = sections or {}
    meta = {
        "title": topic.name,
        "type": "topic",
        "slug": topic.slug,
        "updated_at": friendly_date(),
    }

    source_list = (
        "\n".join(f"- {wikilink(t)}" for t in source_titles)
        if source_titles
        else "- _No sources yet_"
    )
    concept_links = (
        ", ".join(wikilink(c) for c in topic.related_concepts)
        if topic.related_concepts
        else "_None yet_"
    )
    entity_links = (
        ", ".join(wikilink(e) for e in topic.related_entities)
        if topic.related_entities
        else "_None yet_"
    )

    body = f"""# {topic.name}

## Topic Summary

{
        sections.get(
            "Topic Summary",
            topic.summary or "_Summary will be enriched as more sources are added._",
        )
    }

## What I Have Saved

{source_list}

## Core Concepts

{sections.get("Core Concepts", concept_links)}

## Important Entities

{sections.get("Important Entities", entity_links)}

## Patterns Across Sources

{
        sections.get(
            "Patterns Across Sources",
            "_Patterns will emerge as more sources are ingested on this topic._",
        )
    }

## Gaps In My Understanding

{
        sections.get(
            "Gaps In My Understanding",
            "_To be identified through further reading and lint passes._",
        )
    }

## Suggested Learning Path

{
        sections.get(
            "Suggested Learning Path",
            "_Will be generated once enough sources cover this topic._",
        )
    }
"""
    return build_frontmatter_doc(meta, body)


def entity_note_md(
    entity: Entity,
    source_titles: list[str],
    sections: dict[str, str] | None = None,
) -> str:
    sections = sections or {}
    meta = {
        "title": entity.name,
        "type": "entity",
        "entity_type": entity.entity_type,
        "slug": entity.slug,
        "updated_at": friendly_date(),
    }

    mentions = (
        "\n".join(f"- {wikilink(t)}" for t in source_titles)
        if source_titles
        else "- _No mentions yet_"
    )
    concept_links = (
        ", ".join(wikilink(c) for c in entity.related_concepts)
        if entity.related_concepts
        else "_None yet_"
    )

    body = f"""# {entity.name}

## What It Is

{
        sections.get(
            "What It Is",
            entity.description or f"_{entity.entity_type.title()} referenced in saved sources._",
        )
    }

## Why It Shows Up In My Vault

{
        sections.get(
            "Why It Shows Up In My Vault",
            f"Referenced in {len(source_titles)} source(s) in this vault.",
        )
    }

## Related Concepts

{sections.get("Related Concepts", concept_links)}

## Mentioned In

{mentions}
"""
    return build_frontmatter_doc(meta, body)


def concept_note_md(
    concept: Concept,
    source_titles: list[str],
    sections: dict[str, str] | None = None,
) -> str:
    sections = sections or {}
    meta = {
        "title": concept.name,
        "type": "concept",
        "slug": concept.slug,
        "updated_at": friendly_date(),
    }

    sources = (
        "\n".join(f"- {wikilink(t)}" for t in source_titles)
        if source_titles
        else "- _No examples yet_"
    )
    related = (
        ", ".join(wikilink(c) for c in concept.related_concepts)
        if concept.related_concepts
        else "_None yet_"
    )

    body = f"""# {concept.name}

## Definition

{
        sections.get(
            "Definition",
            concept.definition
            or "_Definition will be refined as more sources mention this concept._",
        )
    }

## Where It Appears

{sources}

## Related Concepts

{sections.get("Related Concepts", related)}

## Examples From Saved Sources

{sections.get("Examples From Saved Sources", "_Examples will be extracted as the vault grows._")}
"""
    return build_frontmatter_doc(meta, body)


def synthesis_note_md(note: SynthesisNote) -> str:
    meta = {
        "title": note.title,
        "type": "synthesis",
        "slug": note.slug,
        "created_at": friendly_date(note.created_at),
    }

    basis = (
        "\n".join(f"- {wikilink(s)}" for s in note.source_basis)
        if note.source_basis
        else "- _No sources_"
    )

    body = f"""# {note.title}

## Summary

{note.summary}

## Source Basis

{basis}

## Main Patterns

{note.main_patterns or "_No patterns identified yet._"}

## Conflicts or Tensions

{note.conflicts or "_No conflicts detected._"}

## Recommended Next Steps

{note.next_steps or "_No recommendations yet._"}
"""
    return build_frontmatter_doc(meta, body)


def raw_capture_md(content: SourceContent) -> str:
    meta = {
        "title": content.source.title,
        "type": "raw",
        "source_url": content.source.url,
        "source_type": content.source.source_type.value,
        "captured_at": friendly_date(),
        "immutable": True,
    }
    body = f"""# Raw Capture: {content.source.title}

> This file is an immutable raw capture. Do not edit.

{content.raw_text}
"""
    return build_frontmatter_doc(meta, body)
