"""Tests for the ingest flow using mocked LLM and fetchers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.compiler.ingest_graph import (
    IngestState,
    _analyse_content,
    _extract_knowledge,
    _write_vault,
)
from app.models.db import ProcessedSource
from app.models.source import SourceContent, SourceItem, SourceType


@pytest.fixture
def mock_content() -> SourceContent:
    item = SourceItem(
        url="https://example.com/langchain-guide",
        title="Complete Guide to LangChain",
        source_type=SourceType.ARTICLE,
        tags=["langchain", "ai"],
    )
    return SourceContent(
        source=item,
        raw_text="<html>Full HTML content</html>",
        cleaned_text=(
            "LangChain is a framework for building LLM-powered applications. "
            "It provides tools for chains, agents, and retrieval."
        ),
        author="AI Writer",
        published_date="2025-03-01",
        word_count=20,
        extraction_quality="good",
        content_hash="content123",
        url_hash="url456",
    )


@pytest.fixture
def mock_analysis() -> dict:
    return {
        "summary": "A comprehensive guide to LangChain framework.",
        "key_takeaways": (
            "- LangChain is for LLM apps\n- Supports chains and agents\n- Good for RAG"
        ),
        "detailed_outline": (
            "## Introduction\n- What is LangChain\n## Core Concepts\n- Chains\n- Agents"
        ),
        "important_claims": "- LangChain simplifies LLM development",
        "why_matters": "Understanding LangChain is essential for modern AI development.",
        "open_questions": "- How does it compare to alternatives?",
        "topics": ["LangChain", "LLM Development"],
        "entities": [
            {"name": "LangChain", "type": "tool", "description": "LLM application framework"},
        ],
        "concepts": [
            {"name": "Chain", "definition": "A sequence of LLM calls"},
            {"name": "Agent", "definition": "An autonomous LLM-powered component"},
        ],
    }


class TestAnalyseContent:
    @pytest.mark.asyncio
    async def test_analyse_with_failed_extraction(self, mock_content: SourceContent):
        mock_content.extraction_quality = "failed"
        mock_content.cleaned_text = ""
        state: IngestState = {"item": mock_content.source, "content": mock_content, "slug": "test"}
        result = await _analyse_content(state)
        assert (
            "failed" in result["analysis"]["key_takeaways"].lower()
            or "extraction" in result["analysis"]["summary"].lower()
        )


class TestExtractKnowledge:
    @pytest.mark.asyncio
    async def test_extract_topics(self, mock_analysis: dict):
        state: IngestState = {"item": None, "slug": "test", "analysis": mock_analysis}
        result = await _extract_knowledge(state)
        assert len(result["topics"]) == 2
        assert result["topics"][0].name == "LangChain"

    @pytest.mark.asyncio
    async def test_extract_entities(self, mock_analysis: dict):
        state: IngestState = {"item": None, "slug": "test", "analysis": mock_analysis}
        result = await _extract_knowledge(state)
        assert len(result["entities"]) == 1
        assert result["entities"][0].entity_type == "tool"

    @pytest.mark.asyncio
    async def test_extract_concepts(self, mock_analysis: dict):
        state: IngestState = {"item": None, "slug": "test", "analysis": mock_analysis}
        result = await _extract_knowledge(state)
        assert len(result["concepts"]) == 2


class TestWriteVault:
    @pytest.mark.asyncio
    async def test_writes_all_notes(
        self,
        tmp_vault: Path,
        mock_content: SourceContent,
        mock_analysis: dict,
    ):
        from app.models.knowledge import Concept, Entity, Topic

        topics = [Topic(name="LangChain", slug="langchain")]
        entities = [Entity(name="LangChain", slug="langchain", entity_type="tool")]
        concepts = [Concept(name="Chain", slug="chain", definition="A sequence")]

        state: IngestState = {
            "item": mock_content.source,
            "content": mock_content,
            "slug": "complete-guide-to-langchain",
            "analysis": mock_analysis,
            "topics": topics,
            "entities": entities,
            "concepts": concepts,
        }

        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.vault_path = tmp_vault
            result = await _write_vault(state)

        updates = result["vault_updates"]
        note_types = {u.note_type for u in updates}
        assert "raw_capture" in note_types
        assert "source" in note_types
        assert "topic" in note_types
        assert "entity" in note_types
        assert "concept" in note_types

        source_file = tmp_vault / "wiki" / "sources" / "articles" / "complete-guide-to-langchain.md"
        assert source_file.exists()


class TestDeduplication:
    @pytest.mark.asyncio
    async def test_detects_content_hash_duplicates(
        self,
        tmp_path: Path,
        mock_content: SourceContent,
    ):
        from app.compiler.ingest_graph import _check_dedup
        from app.storage.repositories import SourceRepository
        from app.storage.sqlite import Database

        db_path = tmp_path / "app.db"
        db = Database(db_path)
        db.connect()
        SourceRepository(db).upsert(
            ProcessedSource(
                url="https://example.com/original",
                url_hash="original-hash",
                content_hash=mock_content.content_hash,
                source_type=mock_content.source.source_type.value,
                title="Existing Source",
                source_note_path="wiki/sources/articles/existing-source.md",
                raw_capture_path="inbox/raw/articles/existing-source.md",
            )
        )
        db.close()

        state: IngestState = {
            "item": mock_content.source,
            "content": mock_content,
            "slug": "complete-guide-to-langchain",
        }

        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.db_path = db_path
            result = await _check_dedup(state)

        assert result["deduplicated"] is True
        assert result["result"].source_note_path == "wiki/sources/articles/existing-source.md"
