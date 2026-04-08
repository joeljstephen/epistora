"""Tests for the ingest flow using mocked LLM and fetchers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.backends.models import BackendResponse
from app.compiler.ingest_graph import (
    IngestState,
    _analyse_content,
    _extract_knowledge,
    _prepare_ingest_evidence,
    _write_vault,
    _youtube_transcript_chunks,
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
        extraction_quality="full",
        content_hash="content123",
        url_hash="url456",
    )


@pytest.fixture
def mock_analysis() -> dict:
    return {
        "summary": "A comprehensive guide to LangChain framework.",
        "five_minute_read": "LangChain is a framework for building LLM apps and RAG systems.",
        "detailed_reading_note": (
            "This source walks through LangChain's components and why they matter."
        ),
        "key_ideas": "- LangChain is for LLM apps\n- Supports chains and agents\n- Good for RAG",
        "detailed_outline": (
            "## Introduction\n- What is LangChain\n## Core Concepts\n- Chains\n- Agents"
        ),
        "important_examples": "- Chains and agents are the main abstractions",
        "actionable_takeaways": "- Use LangChain when building LLM workflows",
        "notable_quotes": "- None captured verbatim.",
        "best_for": "- Engineers building LLM applications",
        "consume_recommendation": "Read the original if you need implementation details.",
        "why_it_matters": "Understanding LangChain is essential for modern AI development.",
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
            "failed" in result["analysis"]["key_ideas"].lower()
            or "extraction" in result["analysis"]["summary"].lower()
        )

    @pytest.mark.asyncio
    async def test_analyse_metadata_only_with_excerpt(self, mock_content: SourceContent):
        mock_content.extraction_quality = "metadata_only"
        mock_content.cleaned_text = "Short metadata excerpt from OG description."
        state: IngestState = {"item": mock_content.source, "content": mock_content, "slug": "test"}

        result = await _analyse_content(state)

        assert "Metadata-only capture" in result["analysis"]["summary"]
        assert "Short metadata excerpt" in result["analysis"]["detailed_outline"]

    @pytest.mark.asyncio
    async def test_analyse_backend_failure_keeps_readable_fallback(
        self,
        mock_content: SourceContent,
    ):
        mock_content.source.source_type = SourceType.X_THREAD
        mock_content.cleaned_text = (
            "Someone packaged reverse-engineered design systems into markdown files.\n\n"
            "Here is how to use it:\n"
            "-> Pick a design system\n"
            "-> Copy the DESIGN.md into your project\n"
            "-> Ask your agent to use it\n"
        )
        state: IngestState = {"item": mock_content.source, "content": mock_content, "slug": "test"}

        with patch(
            "app.compiler.ingest_graph.run_structured",
            side_effect=RuntimeError("backend timeout"),
        ):
            result = await _analyse_content(state)

        analysis = result["analysis"]
        assert "Structured auto-analysis failed" in analysis["summary"]
        assert "## What This Source Covers" in analysis["detailed_reading_note"]
        assert "Pick a design system" in analysis["key_ideas"]
        assert "## Here is how to use it" in analysis["detailed_outline"]

    @pytest.mark.asyncio
    async def test_youtube_backend_failure_still_builds_article_style_fallback(self):
        item = SourceItem(
            url="https://www.youtube.com/watch?v=test",
            title="Test Video",
            source_type=SourceType.YOUTUBE,
        )
        content = SourceContent(
            source=item,
            cleaned_text=(
                "## 00:00-05:00\n\nThe speaker explains why they switched careers and how they "
                "approached the job search.\n\n## 05:00-10:00\n\nThe speaker walks through the "
                "best job boards and networking tactics.\n\n## 10:00-15:00\n\nThe speaker closes "
                "with startup lessons and conference advice."
            ),
            extraction_quality="full",
            extraction_method="youtube_transcript_api",
            url_hash="yt-test",
        )
        state: IngestState = {"item": item, "content": content, "slug": "test-video"}

        with patch(
            "app.compiler.ingest_graph.run_structured",
            side_effect=RuntimeError("backend timeout"),
        ):
            result = await _analyse_content(state)

        analysis = result["analysis"]
        assert "**00:00-05:00**" in analysis["five_minute_read"]
        assert "### 05:00-10:00" in analysis["detailed_reading_note"]
        assert "10:00-15:00:" in analysis["key_ideas"]


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

    @pytest.mark.asyncio
    async def test_article_raw_archive_stays_separate_from_source_note(
        self,
        tmp_vault: Path,
        mock_analysis: dict,
    ):
        item = SourceItem(
            url="https://example.com/article/raw-archive",
            title="Readable Article",
            source_type=SourceType.ARTICLE,
            tags=["article"],
        )
        content = SourceContent(
            source=item,
            raw_text="<html>html</html>",
            cleaned_text="Readable article body with several useful details.",
            archived_markdown="# Readable Article\n\nOriginal article body paragraph.",
            raw_capture_kind="readable_article_markdown",
            extraction_quality="full",
            extraction_method="trafilatura",
            url_hash="article-url",
        )
        state: IngestState = {
            "item": item,
            "content": content,
            "slug": "readable-article",
            "analysis": mock_analysis,
            "topics": [],
            "entities": [],
            "concepts": [],
        }

        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.vault_path = tmp_vault
            await _write_vault(state)

        raw_file = tmp_vault / "inbox" / "raw" / "articles" / "readable-article.md"
        source_file = tmp_vault / "wiki" / "sources" / "articles" / "readable-article.md"

        raw_text = raw_file.read_text(encoding="utf-8")
        source_text = source_file.read_text(encoding="utf-8")

        assert "Original article body paragraph." in raw_text
        assert "Original article body paragraph." not in source_text
        assert "Raw archive" in source_text

    @pytest.mark.asyncio
    async def test_youtube_source_note_has_article_style_sections(
        self,
        tmp_vault: Path,
    ):
        item = SourceItem(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            title="Test Video",
            source_type=SourceType.YOUTUBE,
        )
        content = SourceContent(
            source=item,
            cleaned_text="Transcript section text",
            archived_markdown="# Test Video\n\n## Transcript\n\nTranscript section text",
            raw_capture_kind="youtube_transcript",
            extraction_quality="full",
            extraction_method="youtube_transcript_api",
            raw_metadata={
                "transcript_available": True,
                "caption_type": "manual",
                "transcript_source": "youtube_transcript_api",
            },
            url_hash="video-url",
        )
        analysis = {
            "summary": "Video summary",
            "five_minute_read": "Five minute read",
            "detailed_reading_note": "Article version of the video",
            "key_ideas": "- Key idea",
            "detailed_outline": "## Opening\n- Point",
            "important_examples": "- Example",
            "actionable_takeaways": "- Action",
            "notable_quotes": "- None captured verbatim.",
            "best_for": "- Practitioners",
            "consume_recommendation": (
                "You can skim this note first and only watch for tone or demos."
            ),
            "why_it_matters": "Useful reference.",
            "open_questions": "- Follow-up",
            "topics": [],
            "entities": [],
            "concepts": [],
        }
        state: IngestState = {
            "item": item,
            "content": content,
            "slug": "test-video",
            "analysis": analysis,
            "topics": [],
            "entities": [],
            "concepts": [],
        }

        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.vault_path = tmp_vault
            await _write_vault(state)

        source_file = tmp_vault / "wiki" / "sources" / "videos" / "test-video.md"
        raw_file = tmp_vault / "inbox" / "raw" / "videos" / "test-video.md"
        source_text = source_file.read_text(encoding="utf-8")
        raw_text = raw_file.read_text(encoding="utf-8")

        assert "## Detailed Article Version" in source_text
        assert "## Should I Still Watch This?" in source_text
        assert "Transcript available: yes" in source_text
        assert "## Transcript" in raw_text


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


class TestYoutubeIngestEvidence:
    def test_youtube_transcript_chunks_splits_at_section_headers(self):
        parts = []
        for i in range(0, 20, 5):
            parts.append(f"## {i:02d}:00-{i+5:02d}:00\n\n{'word ' * 500}")
        text = "\n\n".join(parts)
        chunks = _youtube_transcript_chunks(text, 4000)
        assert len(chunks) >= 2
        assert all("## " in c for c in chunks)

    @pytest.mark.asyncio
    async def test_prepare_youtube_evidence_uses_segment_digests_when_over_cap(self):
        item = SourceItem(
            url="https://www.youtube.com/watch?v=testcap",
            title="Long Video",
            source_type=SourceType.YOUTUBE,
        )
        content = SourceContent(
            source=item,
            cleaned_text="x",
            extraction_quality="full",
        )
        sections = []
        for i in range(0, 40, 5):
            sections.append(f"## {i:02d}:00-{i+5:02d}:00\n\n{'word ' * 400}")
        long_text = "\n\n".join(sections)

        with patch("app.config.get_settings") as gs:
            mock_settings = MagicMock()
            mock_settings.ingest_evidence_max_chars = 16000
            mock_settings.ingest_youtube_evidence_max_chars = 2000
            mock_settings.ingest_youtube_chunk_chars = 3000
            gs.return_value = mock_settings

            with patch("app.compiler.ingest_graph.run_text", new_callable=AsyncMock) as rt:
                rt.return_value = BackendResponse(success=True, text="Dense digest.")
                evidence, note = await _prepare_ingest_evidence(content, long_text)

        assert "segment digests" in evidence.lower()
        assert "digest" in note.lower()
        assert rt.await_count >= 1
