"""Tests for canonical artifact creation and compatibility."""

from __future__ import annotations

import json
from pathlib import Path

from app.artifacts import build_artifact_bundle, normalize_markdown_list
from app.config import Settings
from app.models.source import SourceContent, SourceItem, SourceType
from app.sinks.json_export import JsonExportSink
from app.sinks.markdown_vault import MarkdownVaultSink
from app.sinks.registry import available_sink_ids, build_default_sink
from app.vault.writer import VaultWriter


def _sample_content() -> SourceContent:
    item = SourceItem(
        url="https://example.com/agent-memory",
        title="Agent Memory Systems",
        source_type=SourceType.ARTICLE,
        tags=["agents", "memory"],
    )
    return SourceContent(
        source=item,
        raw_text="<html>raw</html>",
        cleaned_text=(
            "Agent memory systems help long-running agents retain facts, state, "
            "and plans across tasks."
        ),
        archived_markdown="# Agent Memory Systems\n\nLong-form article body.",
        raw_capture_kind="readable_article_markdown",
        author="Researcher",
        published_date="2026-03-01",
        word_count=16,
        extraction_quality="full",
        extraction_method="trafilatura",
        extraction_fallback_chain=["httpx", "trafilatura"],
        content_hash="artifact-hash",
        url_hash="artifact-url-hash",
    )


def _sample_analysis() -> dict[str, object]:
    return {
        "summary": "A source about how agent memory improves long-running workflows.",
        "five_minute_read": "Memory lets agents retain useful state.",
        "detailed_reading_note": "The article compares short-term and durable memory layers.",
        "key_ideas": "- Memory improves task continuity\n- Durable state reduces repetition",
        "detailed_outline": "## Overview\n- What memory does\n## Tradeoffs\n- Cost and drift",
        "important_examples": "- A coding agent resuming work after interruption",
        "actionable_takeaways": "- Persist only durable state\n- Keep evidence inspectable",
        "notable_quotes": '- "Good memory reduces repeated work."',
        "best_for": "- Agent builders\n- Workflow designers",
        "consume_recommendation": "Read the original if you need the full examples.",
        "why_it_matters": "Memory quality shapes the reliability of agent systems.",
        "open_questions": "- How should memory expire?",
        "topics": ["Agent Memory"],
        "entities": [
            {"name": "OpenAI", "type": "company", "description": "Builds agent systems"},
        ],
        "concepts": [
            {"name": "Durable memory", "definition": "Persistent state across tasks"},
        ],
    }


def test_normalize_markdown_list_handles_bullets_and_paragraphs():
    value = "- First item\n- Second item\nContinuation detail\n\nStandalone paragraph"
    normalized = normalize_markdown_list(value)
    assert normalized == [
        "First item",
        "Second item Continuation detail",
        "Standalone paragraph",
    ]


def test_build_artifact_bundle_creates_core_artifacts():
    bundle = build_artifact_bundle(
        content=_sample_content(),
        slug="agent-memory-systems",
        analysis=_sample_analysis(),
    )

    assert bundle.source.id == "source:agent-memory-systems"
    assert bundle.source.topic_ids == ["topic:agent-memory"]
    assert bundle.source.entity_ids == ["entity:openai"]
    assert bundle.source.concept_ids == ["concept:durable-memory"]
    assert bundle.evidence_references[0].source_id == bundle.source.id
    assert any(rel.relationship_type == "belongs_to_topic" for rel in bundle.relationships)
    assert any(rel.relationship_type == "mentions_entity" for rel in bundle.relationships)
    assert any(rel.relationship_type == "mentions_concept" for rel in bundle.relationships)


def test_build_artifact_bundle_reuses_existing_titles():
    bundle = build_artifact_bundle(
        content=_sample_content(),
        slug="agent-memory-systems",
        analysis={
            **_sample_analysis(),
            "topics": ["AI cybersecurity"],
            "entities": [{"name": "Project GlassWing", "type": "tool", "description": "tool"}],
            "concepts": [{"name": "Scarcity of elite attention", "definition": "concept"}],
        },
        existing_lookup={
            "topic": {"aicybersecurity": "AI cybersecurity"},
            "entity": {"projectglasswing": "Project Glass Wing"},
            "concept": {"scarcityofeliteattention": "Scarcity of elite attention"},
        },
    )

    assert bundle.topics[0].title == "AI cybersecurity"
    assert bundle.entities[0].title == "Project Glass Wing"
    assert bundle.concepts[0].title == "Scarcity of elite attention"


def test_writer_renders_current_vault_output_from_artifacts(tmp_vault: Path):
    writer = VaultWriter(tmp_vault)
    writer.ensure_structure()

    content = _sample_content()
    bundle = build_artifact_bundle(
        content=content,
        slug="agent-memory-systems",
        analysis=_sample_analysis(),
    )

    updates = writer.write_artifact_bundle(content=content, bundle=bundle)

    note_types = {update.note_type for update in updates}
    assert {"raw_capture", "source", "topic", "entity", "concept"} <= note_types

    source_note = tmp_vault / "wiki" / "sources" / "articles" / "agent-memory-systems.md"
    topic_note = tmp_vault / "wiki" / "topics" / "agent-memory.md"

    source_text = source_note.read_text(encoding="utf-8")
    topic_text = topic_note.read_text(encoding="utf-8")

    assert "## Key Ideas" in source_text
    assert "[[Agent Memory]]" in source_text
    assert "[[OpenAI]]" in source_text
    assert "[[Durable memory]]" in source_text
    assert "[[Agent Memory Systems]]" in topic_text


def test_markdown_vault_sink_matches_writer_wrapper_output(tmp_path: Path):
    sink_vault = tmp_path / "sink-vault"
    writer_vault = tmp_path / "writer-vault"

    content = _sample_content()
    bundle = build_artifact_bundle(
        content=content,
        slug="agent-memory-systems",
        analysis=_sample_analysis(),
    )

    sink = MarkdownVaultSink(sink_vault)
    sink.publish(content=content, bundle=bundle)

    writer = VaultWriter(writer_vault)
    writer.publish(content=content, bundle=bundle)

    sink_files = sorted(
        path.relative_to(sink_vault)
        for path in sink_vault.rglob("*.md")
    )
    writer_files = sorted(
        path.relative_to(writer_vault)
        for path in writer_vault.rglob("*.md")
    )

    assert sink_files == writer_files

    for relative_path in sink_files:
        sink_text = (sink_vault / relative_path).read_text(encoding="utf-8")
        writer_text = (writer_vault / relative_path).read_text(encoding="utf-8")
        assert sink_text == writer_text


def test_json_export_sink_writes_deterministic_bundle_output(tmp_vault: Path):
    content = _sample_content()
    bundle = build_artifact_bundle(
        content=content,
        slug="agent-memory-systems",
        analysis=_sample_analysis(),
    )
    sink = JsonExportSink(tmp_vault, tmp_vault / ".system" / "exports" / "json")

    first_updates = sink.publish(content=content, bundle=bundle)
    export_path = (
        tmp_vault
        / ".system"
        / "exports"
        / "json"
        / "article"
        / "agent-memory-systems.json"
    )
    first_text = export_path.read_text(encoding="utf-8")
    second_updates = sink.publish(content=content, bundle=bundle)
    second_text = export_path.read_text(encoding="utf-8")

    assert len(first_updates) == 1
    assert first_updates[0].path == ".system/exports/json/article/agent-memory-systems.json"
    assert first_updates[0].action == "created"
    assert first_updates[0].note_type == "json_export"
    assert len(second_updates) == 1
    assert second_updates[0].path == ".system/exports/json/article/agent-memory-systems.json"
    assert second_updates[0].action == "updated"
    assert second_updates[0].note_type == "json_export"
    assert first_text == second_text

    payload = json.loads(first_text)
    assert payload["schema_version"] == "epistora.json_export.v1"
    assert payload["export"] == {
        "sink_id": "json_export",
        "source_artifact_id": "source:agent-memory-systems",
        "source_slug": "agent-memory-systems",
        "source_type": "article",
    }
    assert payload["artifact_counts"] == {
        "concepts": 1,
        "entities": 1,
        "evidence_references": 1,
        "relationships": len(bundle.relationships),
        "synthesis": 0,
        "topics": 1,
    }
    assert payload["bundle"]["source"]["title"] == "Agent Memory Systems"
    assert payload["bundle"]["topics"][0]["id"] == "topic:agent-memory"
    assert payload["bundle"]["entities"][0]["id"] == "entity:openai"
    assert payload["bundle"]["concepts"][0]["id"] == "concept:durable-memory"


def test_json_export_sink_uses_canonical_bundle_not_mutated_content(tmp_vault: Path):
    content = _sample_content()
    bundle = build_artifact_bundle(
        content=content,
        slug="agent-memory-systems",
        analysis=_sample_analysis(),
    )
    mutated_content = content.model_copy(
        update={
            "source": content.source.model_copy(update={"title": "Mutated source title"})
        }
    )
    sink = JsonExportSink(tmp_vault, tmp_vault / ".system" / "exports" / "json")

    sink.publish(content=mutated_content, bundle=bundle)

    export_path = (
        tmp_vault
        / ".system"
        / "exports"
        / "json"
        / "article"
        / "agent-memory-systems.json"
    )
    payload = json.loads(export_path.read_text(encoding="utf-8"))

    assert payload["bundle"]["source"]["title"] == "Agent Memory Systems"
    assert payload["bundle"]["source"]["title"] != mutated_content.source.title


def test_json_export_sink_supports_export_root_outside_vault(tmp_path: Path):
    vault_path = tmp_path / "vault"
    export_root = tmp_path / "external-json-exports"
    content = _sample_content()
    bundle = build_artifact_bundle(
        content=content,
        slug="agent-memory-systems",
        analysis=_sample_analysis(),
    )
    sink = JsonExportSink(vault_path, export_root)

    updates = sink.publish(content=content, bundle=bundle)

    export_path = export_root / "article" / "agent-memory-systems.json"
    assert export_path.exists()
    assert len(updates) == 1
    assert updates[0].path == str(export_path)
    assert updates[0].action == "created"
    assert updates[0].note_type == "json_export"


def test_default_sink_supports_markdown_and_json_export_coexistence(tmp_path: Path):
    vault_path = tmp_path / "vault"
    content = _sample_content()
    bundle = build_artifact_bundle(
        content=content,
        slug="agent-memory-systems",
        analysis=_sample_analysis(),
    )
    settings = Settings(
        vault_path=vault_path,
        artifact_sink_ids=" markdown_vault, json_export, markdown_vault ",
    )

    assert settings.configured_artifact_sink_ids == ["markdown_vault", "json_export"]
    assert {"markdown_vault", "json_export"} <= set(available_sink_ids(settings))

    sink = build_default_sink(settings)
    updates = sink.publish(content=content, bundle=bundle)

    assert (vault_path / "wiki" / "sources" / "articles" / "agent-memory-systems.md").exists()
    assert (
        vault_path
        / ".system"
        / "exports"
        / "json"
        / "article"
        / "agent-memory-systems.json"
    ).exists()
    assert any(update.note_type == "json_export" for update in updates)
    assert any(update.note_type == "source" for update in updates)
