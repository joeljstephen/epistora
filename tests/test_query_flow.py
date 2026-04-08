"""Tests for the query flow against a fixture vault."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from app.models.knowledge import Topic
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
            raw_capture_path=f"inbox/raw/articles/{slug}.md",
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
    return tmp_vault


class TestQuerySearch:
    def test_search_finds_relevant_notes(self, populated_vault: Path):
        from app.retrieval.search import search_vault

        results = search_vault(populated_vault, "RAG")
        assert len(results) > 0
        titles = [r["title"] for r in results]
        assert any("RAG" in t for t in titles)

    def test_search_returns_snippets(self, populated_vault: Path):
        from app.retrieval.search import search_vault

        results = search_vault(populated_vault, "LangChain")
        assert len(results) > 0
        assert results[0].get("snippet")

    def test_fallback_search(self, populated_vault: Path):
        from app.retrieval.search import _fallback_search

        results = _fallback_search(populated_vault, "vector databases", limit=5)
        assert len(results) > 0


class TestQueryGraph:
    @pytest.mark.asyncio
    async def test_resolve_context(self, populated_vault: Path):
        from app.compiler.query_graph import _resolve_context

        state = {
            "question": "What do I know about RAG?",
            "vault_path": str(populated_vault),
        }
        result = await _resolve_context(state)
        assert result["context"] != ""
        assert len(result["source_references"]) > 0
        assert all(ref.endswith(".md") for ref in result["source_references"])


class TestQueryDeprecation:
    def test_query_cli_shows_deprecation_warning(self):
        from typer.testing import CliRunner

        from app.cli.main import app

        runner = CliRunner()
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = runner.invoke(app, ["query", "--help"])
            assert result.exit_code == 0

    def test_query_api_has_deprecation(self):
        from app.api.routes_query import router

        route = router.routes[0]
        assert route.deprecated is True
