"""Tests for the v2-native retrieval and query flow."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.models.knowledge import Topic
from app.read_model import ReadModelStore
from app.retrieval import build_retrieval_context
from app.vault.index_updater import rebuild_indexes
from app.vault.writer import VaultWriter


@pytest.fixture
def populated_vault(tmp_vault: Path) -> Path:
    """Create a vault with some fixture notes for query testing."""
    writer = VaultWriter(tmp_vault)

    from app.models.source import SourceContent, SourceItem, SourceType

    for i, (title, url) in enumerate(
        [
            ("Introduction to RAG", "https://example.com/rag-intro"),
            ("LangChain Deep Dive", "https://example.com/langchain-deep"),
            ("Vector Databases Explained", "https://example.com/vectordb"),
        ]
    ):
        item = SourceItem(url=url, title=title, source_type=SourceType.ARTICLE)
        content = SourceContent(
            source=item,
            raw_text=f"Raw content for {title}",
            cleaned_text=f"Detailed content about {title}. Covers important concepts.",
            word_count=10,
            extraction_quality="full",
            content_hash=f"hash{i}",
            url_hash=f"urlhash{i}",
        )
        slug = title.lower().replace(" ", "-")
        writer.write_raw_capture(content, slug)
        writer.write_source_note(
            content=content,
            slug=slug,
            raw_capture_path=f"raw/articles/{slug}.md",
            summary=f"Summary of {title}",
            five_minute_read=f"Briefing for {title}",
            detailed_reading_note=f"Detailed reading note for {title}",
            key_ideas=f"- Key point about {title}",
            detailed_outline=f"## Overview of {title}",
            important_examples=f"- Example from {title}",
            actionable_takeaways=f"- Apply ideas from {title}",
            notable_quotes="- None captured verbatim.",
            best_for=f"- Readers learning about {title}",
            consume_recommendation=f"Read {title} for more depth.",
            why_it_matters=f"{title} matters for AI development",
            open_questions=f"- More to explore about {title}",
            topics=["RAG", "AI"],
            entities=[],
            concepts=["Retrieval Augmented Generation"],
        )

    topic = Topic(name="RAG", slug="rag", summary="Retrieval Augmented Generation")
    writer.write_topic(topic, ["Introduction to RAG", "LangChain Deep Dive"])

    rebuild_indexes(tmp_vault)
    ReadModelStore(tmp_vault).rebuild()
    return tmp_vault


class TestReadModelRetrieval:
    def test_structured_resolution_centers_on_read_model(self, populated_vault: Path):
        context = build_retrieval_context(populated_vault, "What do I know about RAG?")

        assert context.artifacts
        assert any(artifact.note.note_type == "topic" for artifact in context.artifacts)
        assert any(ref.endswith(".md") for ref in context.source_references)

    def test_lexical_support_is_available_from_read_model(self, populated_vault: Path):
        results = ReadModelStore(populated_vault).search_lexical("LangChain", limit=5)

        assert results
        assert results[0]["snippet"]

    def test_relationship_expansion_pulls_supporting_sources(self, populated_vault: Path):
        context = build_retrieval_context(populated_vault, "RAG")
        note_types = {artifact.note.note_type for artifact in context.artifacts}

        assert "topic" in note_types
        assert "source" in note_types


class TestQueryService:
    def test_query_context_contains_rendered_context(self, populated_vault: Path):
        from app.services.query_service import _resolve_context

        result = _resolve_context(vault_path=populated_vault, question="What do I know about RAG?")
        assert result.text_context != ""
        assert result.source_references
        assert all(ref.endswith(".md") for ref in result.source_references)


class TestQueryInterfaces:
    def test_query_cli_help_is_available(self):
        from typer.testing import CliRunner

        from app.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["query", "--help"])
        assert result.exit_code == 0
        assert "query" in result.output.lower()

    def test_query_api_is_not_marked_deprecated(self):
        from app.api.routes_query import router

        route = router.routes[0]
        assert not route.deprecated
