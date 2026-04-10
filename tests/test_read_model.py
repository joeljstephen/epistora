"""Tests for the derived local read model."""

from __future__ import annotations

from pathlib import Path

from app.artifacts import build_artifact_bundle
from app.models.source import SourceContent, SourceItem, SourceType
from app.read_model import (
    RELATION_SOURCE_CONCEPT,
    RELATION_SOURCE_ENTITY,
    RELATION_SOURCE_TOPIC,
    RELATION_WIKILINK,
    ReadModelStore,
)
from app.sinks.markdown_vault import MarkdownVaultSink
from app.vault.writer import VaultWriter


def _sample_content(title: str, url: str) -> SourceContent:
    item = SourceItem(
        url=url,
        title=title,
        source_type=SourceType.ARTICLE,
        tags=["ai"],
    )
    return SourceContent(
        source=item,
        raw_text="<html>raw</html>",
        cleaned_text=f"{title} content about agents, memory, and retrieval.",
        archived_markdown=f"# {title}\n\nReadable article body.",
        raw_capture_kind="readable_article_markdown",
        extraction_quality="full",
        extraction_method="trafilatura",
        content_hash=f"{title}-hash",
        url_hash=f"{title}-url-hash",
    )


def _analysis(
    *,
    topics: list[str],
    entities: list[dict],
    concepts: list[dict],
) -> dict[str, object]:
    return {
        "summary": "Summary",
        "five_minute_read": "Briefing",
        "detailed_reading_note": "Detailed note",
        "key_ideas": "- Key idea",
        "detailed_outline": "## Overview\n- Point",
        "important_examples": "- Example",
        "actionable_takeaways": "- Action",
        "notable_quotes": "- None captured verbatim.",
        "best_for": "- Builders",
        "consume_recommendation": "Read the original for more detail.",
        "why_it_matters": "It matters.",
        "open_questions": "- Question",
        "topics": topics,
        "entities": entities,
        "concepts": concepts,
    }


def test_read_model_rebuild_populates_note_catalog(tmp_vault: Path):
    writer = VaultWriter(tmp_vault)
    content = _sample_content("Agent Memory Systems", "https://example.com/agent-memory")

    writer.write_raw_capture(content, "agent-memory-systems")
    writer.write_source_note(
        content=content,
        slug="agent-memory-systems",
        raw_capture_path="raw/articles/agent-memory-systems.md",
        summary="Summary",
        five_minute_read="Briefing",
        detailed_reading_note="Detailed note",
        key_ideas="- Key idea",
        detailed_outline="## Overview\n- Point",
        important_examples="- Example",
        actionable_takeaways="- Action",
        notable_quotes="- None captured verbatim.",
        best_for="- Builders",
        consume_recommendation="Read the original for more detail.",
        why_it_matters="It matters.",
        open_questions="- Question",
        topics=["Agent Memory"],
        entities=["OpenAI"],
        concepts=["Durable memory"],
    )

    store = ReadModelStore(tmp_vault)
    result = store.rebuild()

    assert result["notes"] >= 2
    notes = store.list_notes()
    note_paths = {note.note_path for note in notes}
    assert "raw/articles/agent-memory-systems.md" in note_paths
    assert "wiki/sources/articles/agent-memory-systems.md" in note_paths
    source_note = store.get_note("wiki/sources/articles/agent-memory-systems.md")
    assert source_note is not None
    assert source_note.note_type == "source"
    assert source_note.indexed_at is not None
    assert store.get_state("last_full_rebuild_at") is not None


def test_read_model_rebuild_creates_edges_and_backlinks(tmp_vault: Path):
    sink = MarkdownVaultSink(tmp_vault)
    content = _sample_content("Agent Memory Systems", "https://example.com/agent-memory")
    bundle = build_artifact_bundle(
        content=content,
        slug="agent-memory-systems",
        analysis=_analysis(
            topics=["Agent Memory"],
            entities=[{"name": "OpenAI", "type": "company", "description": "AI company"}],
            concepts=[{"name": "Durable memory", "definition": "persistent state"}],
        ),
    )

    sink.publish(content=content, bundle=bundle)

    store = ReadModelStore(tmp_vault)
    source_path = "wiki/sources/articles/agent-memory-systems.md"
    topic_path = "wiki/topics/agent-memory.md"

    wikilinks = store.get_edges(from_note_path=source_path, relation_type=RELATION_WIKILINK)
    source_topics = store.get_edges(
        from_note_path=source_path,
        relation_type=RELATION_SOURCE_TOPIC,
    )
    source_entities = store.get_edges(
        from_note_path=source_path,
        relation_type=RELATION_SOURCE_ENTITY,
    )
    source_concepts = store.get_edges(
        from_note_path=source_path,
        relation_type=RELATION_SOURCE_CONCEPT,
    )
    backlinks = store.get_backlinks(topic_path)

    assert any(edge.to_note_path == topic_path for edge in wikilinks)
    assert any(edge.target_title == "Agent Memory" for edge in source_topics)
    assert any(edge.target_title == "OpenAI" for edge in source_entities)
    assert any(edge.target_title == "Durable memory" for edge in source_concepts)
    assert any(edge.from_note_path == source_path for edge in backlinks)


def test_read_model_incremental_refresh_updates_edges(tmp_vault: Path):
    sink = MarkdownVaultSink(tmp_vault)
    content = _sample_content("Agent Memory Systems", "https://example.com/agent-memory")

    first_bundle = build_artifact_bundle(
        content=content,
        slug="agent-memory-systems",
        analysis=_analysis(
            topics=["Agent Memory"],
            entities=[],
            concepts=[],
        ),
    )
    sink.publish(content=content, bundle=first_bundle)

    store = ReadModelStore(tmp_vault)
    source_path = "wiki/sources/articles/agent-memory-systems.md"
    assert any(
        edge.target_title == "Agent Memory"
        for edge in store.get_edges(from_note_path=source_path, relation_type=RELATION_SOURCE_TOPIC)
    )

    second_bundle = build_artifact_bundle(
        content=content,
        slug="agent-memory-systems",
        analysis=_analysis(
            topics=["Agents"],
            entities=[],
            concepts=[],
        ),
    )
    sink.publish(content=content, bundle=second_bundle)

    refreshed_edges = store.get_edges(
        from_note_path=source_path,
        relation_type=RELATION_SOURCE_TOPIC,
    )
    assert any(edge.target_title == "Agents" for edge in refreshed_edges)
    assert not any(edge.target_title == "Agent Memory" for edge in refreshed_edges)
    assert store.get_state("last_incremental_refresh_at") is not None


def test_read_model_rebuild_from_existing_vault_state(tmp_vault: Path):
    writer = VaultWriter(tmp_vault)
    first = _sample_content("First Source", "https://example.com/first")
    second = _sample_content("Second Source", "https://example.com/second")

    for slug, content in [
        ("first-source", first),
        ("second-source", second),
    ]:
        writer.write_raw_capture(content, slug)
        writer.write_source_note(
            content=content,
            slug=slug,
            raw_capture_path=f"raw/articles/{slug}.md",
            summary="Summary",
            five_minute_read="Briefing",
            detailed_reading_note="Detailed note",
            key_ideas="- Key idea",
            detailed_outline="## Overview\n- Point",
            important_examples="- Example",
            actionable_takeaways="- Action",
            notable_quotes="- None captured verbatim.",
            best_for="- Builders",
            consume_recommendation="Read the original for more detail.",
            why_it_matters="It matters.",
            open_questions="- Question",
            topics=["Shared Topic"],
            entities=[],
            concepts=[],
        )

    store = ReadModelStore(tmp_vault)
    result = store.rebuild()

    assert result["notes"] >= 4
    source_notes = store.list_notes(note_type="source")
    assert len(source_notes) == 2
    assert all(note.note_path.startswith("wiki/sources/articles/") for note in source_notes)
