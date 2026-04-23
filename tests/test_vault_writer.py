"""Tests for vault writing operations."""

from pathlib import Path

import pytest

from app.artifacts import build_artifact_bundle
from app.models.knowledge import Concept, Entity, Topic
from app.models.lifecycle import LifecycleMetadata
from app.models.source import (
    DerivedWorkKind,
    SourceContent,
    SourceItem,
    SourceType,
)
from app.storage.evidence import EvidenceStoragePolicy
from app.utils.markdown import build_frontmatter_doc, parse_frontmatter
from app.vault.writer import VaultWriter


@pytest.fixture
def writer(tmp_vault: Path) -> VaultWriter:
    return VaultWriter(tmp_vault)


@pytest.fixture
def content() -> SourceContent:
    item = SourceItem(
        url="https://example.com/test-article",
        title="Test Article About AI",
        source_type=SourceType.ARTICLE,
        tags=["ai", "testing"],
    )
    return SourceContent(
        source=item,
        raw_text="Raw HTML content here",
        cleaned_text="Cleaned article text about AI and testing.",
        author="Test Author",
        published_date="2025-06-01",
        word_count=7,
        extraction_quality="full",
        content_hash="hash123",
        url_hash="urlhash456",
    )


class TestVaultWriter:
    def test_write_raw_capture(self, writer: VaultWriter, content: SourceContent):
        update = writer.write_raw_capture(content, "test-article-about-ai")
        assert update.action == "created"
        assert update.note_type == "raw_capture"
        path = writer.vault_path / update.path
        assert path.exists()
        text = path.read_text()
        assert "immutable" in text.lower()
        assert content.source.url in text

    def test_write_source_note(self, writer: VaultWriter, content: SourceContent):
        update = writer.write_source_note(
            content=content,
            slug="test-article-about-ai",
            raw_capture_path="raw/articles/test-article-about-ai.md",
            quick_brief="A quick orientation to the article.",
            summary="A test summary",
            five_minute_read="A five minute read",
            detailed_reading_note="A detailed reading note",
            best_next_action="Read the brief first, then open the original if needed.",
            theme_tags=["agentic-ai"],
            brief_status="ready",
            key_ideas="- Key point 1\n- Key point 2",
            detailed_outline="## Section 1\n- Detail",
            important_examples="- Claim A",
            actionable_takeaways="- Try this in practice",
            notable_quotes="- None captured verbatim.",
            best_for="- Builders",
            consume_recommendation="Read the original for more detail.",
            why_it_matters="This matters because testing.",
            open_questions="- What about edge cases?",
            topics=["AI", "Testing"],
            entities=["Test Author"],
            concepts=["Unit Testing"],
        )
        assert update.action == "created"
        path = writer.vault_path / update.path
        assert path.exists()
        text = path.read_text()
        assert "Test Article About AI" in text
        assert "[[AI]]" in text
        assert "[[Test Author]]" in text
        assert "source_url" in text
        assert "## Overview" in text
        assert "## Best Next Action" in text
        meta, _ = parse_frontmatter(text)
        assert meta["lifecycle"]["staleness_status"] == "unknown"
        assert meta["lifecycle"]["reinforcement_count"] == 0
        assert meta["brief_status"] == "ready"
        assert meta["theme_tags"] == ["agentic-ai"]

    def test_write_generic_source_note_to_misc(self, writer: VaultWriter):
        item = SourceItem(
            url="https://example.com/docs",
            title="Docs Home",
            source_type=SourceType.GENERIC,
        )
        content = SourceContent(
            source=item,
            raw_text="Raw docs content",
            cleaned_text="Docs landing page content.",
            extraction_quality="partial",
            url_hash="generic-urlhash",
        )

        update = writer.write_source_note(
            content=content,
            slug="docs-home",
            raw_capture_path="raw/misc/docs-home.md",
            quick_brief="Summary",
            summary="Summary",
            five_minute_read="Briefing",
            detailed_reading_note="Detailed note",
            key_ideas="- Docs",
            detailed_outline="Overview",
            important_examples="- Claim",
            actionable_takeaways="- Action",
            notable_quotes="- None captured verbatim.",
            best_for="- Readers",
            consume_recommendation="Open the source if needed.",
            why_it_matters="Why it matters",
            open_questions="- Question",
            topics=[],
            entities=[],
            concepts=[],
        )

        assert update.path == "wiki/sources/misc/docs-home.md"

    def test_write_source_note_falls_back_to_url_when_title_missing(self, writer: VaultWriter):
        item = SourceItem(
            url="https://example.com/missing-title",
            title="",
            source_type=SourceType.GENERIC,
        )
        content = SourceContent(
            source=item,
            raw_text="Raw content",
            cleaned_text="Cleaned content",
            extraction_quality="failed",
            url_hash="missing-title-hash",
        )

        update = writer.write_source_note(
            content=content,
            slug="missing-title",
            raw_capture_path="raw/misc/missing-title.md",
            quick_brief="Summary",
            summary="Summary",
            five_minute_read="Briefing",
            detailed_reading_note="Detailed note",
            key_ideas="- Takeaway",
            detailed_outline="Outline",
            important_examples="- Claim",
            actionable_takeaways="- Action",
            notable_quotes="- None captured verbatim.",
            best_for="- Readers",
            consume_recommendation="Open the source if needed.",
            why_it_matters="Why",
            open_questions="- Question",
            topics=[],
            entities=[],
            concepts=[],
        )

        text = (writer.vault_path / update.path).read_text(encoding="utf-8")
        assert "title: https://example.com/missing-title" in text
        assert "# https://example.com/missing-title" in text

    def test_write_derived_work_source_note_uses_derived_paths_and_lifecycle(
        self,
        writer: VaultWriter,
    ):
        item = SourceItem(
            url="epistora://sessions/analysis-1",
            title="Architecture Analysis",
            source_type=SourceType.DERIVED_WORK,
            derived_work_kind=DerivedWorkKind.DERIVED_ANALYSIS,
        )
        content = SourceContent(
            source=item,
            raw_text="Working notes",
            cleaned_text="Structured analysis of the maintenance architecture.",
            archived_markdown="# Analysis\n\nWorking notes",
            extraction_quality="full",
            url_hash="derived-analysis-1",
            derived_work_kind=DerivedWorkKind.DERIVED_ANALYSIS,
            lifecycle=LifecycleMetadata(
                confidence=0.82,
                last_confirmed_at="2026-04-10T00:00:00+00:00",
                supersedes=["wiki/synthesis/old-analysis.md"],
                reinforcement_count=2,
            ),
        )

        raw_update = writer.write_raw_capture(content, "architecture-analysis")
        source_update = writer.write_source_note(
            content=content,
            slug="architecture-analysis",
            raw_capture_path=raw_update.path,
            quick_brief="A durable analysis artifact.",
            summary="A durable analysis artifact.",
            five_minute_read="Short brief.",
            detailed_reading_note="Longer note.",
            key_ideas="- Durable output",
            detailed_outline="## Outline\n- Point",
            important_examples="- Example",
            actionable_takeaways="- Follow up",
            notable_quotes="- None captured verbatim.",
            best_for="- Maintainers",
            consume_recommendation="Read when updating maintenance.",
            why_it_matters="This preserves work-derived knowledge.",
            open_questions="- Should this be promoted?",
            topics=["Maintenance"],
            entities=[],
            concepts=["Derived Knowledge"],
        )

        assert raw_update.path == "raw/derived/architecture-analysis.md"
        assert source_update.path == "wiki/sources/derived/architecture-analysis.md"

        meta, _ = parse_frontmatter(
            (writer.vault_path / source_update.path).read_text(encoding="utf-8")
        )
        assert meta["source_type"] == "derived_work"
        assert meta["derived_work_kind"] == "derived_analysis"
        assert meta["lifecycle"]["confidence"] == 0.82
        assert meta["lifecycle"]["supersedes"] == ["wiki/synthesis/old-analysis.md"]
        assert meta["lifecycle"]["reinforcement_count"] == 2

    def test_write_source_note_preserves_user_state_overrides(
        self,
        writer: VaultWriter,
        content: SourceContent,
    ):
        update = writer.write_source_note(
            content=content,
            slug="test-article-about-ai",
            raw_capture_path="raw/articles/test-article-about-ai.md",
            quick_brief="A quick orientation to the article.",
            summary="A test summary",
            five_minute_read="A five minute read",
            detailed_reading_note="A detailed reading note",
            best_next_action="Read the brief first, then open the original if needed.",
            theme_tags=["agentic-ai"],
            brief_status="ready",
            key_ideas="- Key point 1\n- Key point 2",
            detailed_outline="## Section 1\n- Detail",
            important_examples="- Claim A",
            actionable_takeaways="- Try this in practice",
            notable_quotes="- None captured verbatim.",
            best_for="- Builders",
            consume_recommendation="Read the original for more detail.",
            why_it_matters="This matters because testing.",
            open_questions="- What about edge cases?",
            topics=["AI", "Testing"],
            entities=["Test Author"],
            concepts=["Unit Testing"],
        )

        path = writer.vault_path / update.path
        original = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(original)
        meta["user_state"] = {"reading_state": "review", "review_excluded": True}
        path.write_text(build_frontmatter_doc(meta, body), encoding="utf-8")

        writer.write_source_note(
            content=content,
            slug="test-article-about-ai",
            raw_capture_path="raw/articles/test-article-about-ai.md",
            quick_brief="Updated orientation.",
            summary="Updated summary",
            five_minute_read="Updated briefing",
            detailed_reading_note="Updated note",
            best_next_action="Skim the brief only unless this becomes active.",
            theme_tags=["agentic-ai"],
            brief_status="ready",
            key_ideas="- Updated key point",
            detailed_outline="## Updated\n- Detail",
            important_examples="- Updated example",
            actionable_takeaways="- Updated action",
            notable_quotes="- None captured verbatim.",
            best_for="- Updated audience",
            consume_recommendation="The brief may be enough for now.",
            why_it_matters="Updated why",
            open_questions="- Updated question",
            topics=["AI", "Testing"],
            entities=["Test Author"],
            concepts=["Unit Testing"],
        )

        updated_meta, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        assert updated_meta["user_state"] == {"reading_state": "review", "review_excluded": True}
        assert updated_meta["reading_state"] == "review"

    def test_write_topic(self, writer: VaultWriter):
        topic = Topic(name="Machine Learning", slug="machine-learning", summary="ML is cool")
        update = writer.write_topic(topic, ["Source A"])
        assert update.action == "created"
        path = writer.vault_path / update.path
        text = path.read_text()
        assert "Machine Learning" in text
        assert "[[Source A]]" in text

    def test_update_topic_merges_sources(self, writer: VaultWriter):
        topic = Topic(name="Machine Learning", slug="machine-learning", summary="ML is cool")
        writer.write_topic(topic, ["Source A"])
        update = writer.write_topic(topic, ["Source B"])
        assert update.action == "updated"
        text = (writer.vault_path / update.path).read_text()
        assert "[[Source A]]" in text
        assert "[[Source B]]" in text

    def test_write_entity(self, writer: VaultWriter):
        entity = Entity(
            name="OpenAI", slug="openai", entity_type="company", description="AI company"
        )
        update = writer.write_entity(entity, ["Article 1"])
        path = writer.vault_path / update.path
        text = path.read_text()
        assert "OpenAI" in text
        assert "company" in text.lower()
        assert "wiki/entities/companies/" in update.path

    def test_write_concept(self, writer: VaultWriter):
        concept = Concept(
            name="Backpropagation", slug="backpropagation", definition="A learning algorithm"
        )
        update = writer.write_concept(concept, ["Deep Learning Intro"])
        path = writer.vault_path / update.path
        text = path.read_text()
        assert "Backpropagation" in text
        assert "learning algorithm" in text.lower()

    def test_overwrite_updates_action(self, writer: VaultWriter, content: SourceContent):
        writer.write_raw_capture(content, "test-slug")
        update = writer.write_raw_capture(content, "test-slug")
        assert update.action == "unchanged"

    def test_large_raw_capture_uses_blob_storage(self, tmp_vault: Path):
        writer = VaultWriter(
            tmp_vault,
            storage_policy=EvidenceStoragePolicy(
                blob_threshold_bytes=200,
                blob_preview_chars=120,
            ),
        )
        item = SourceItem(
            url="https://example.com/large-transcript",
            title="Large Transcript",
            source_type=SourceType.YOUTUBE,
        )
        transcript = "## 00:00-05:00\n\n" + ("Long transcript line.\n" * 600)
        content = SourceContent(
            source=item,
            raw_text=transcript,
            cleaned_text=transcript,
            archived_markdown=f"# Large Transcript\n\n{transcript}",
            raw_capture_kind="youtube_transcript",
            extraction_quality="full",
            extraction_method="youtube_transcript_api",
            raw_metadata={"transcript_available": True},
            url_hash="large-transcript",
        )

        updates = writer.write_artifact_bundle(
            content=content,
            bundle=build_artifact_bundle(
                content=content,
                slug="large-transcript",
                analysis={
                    "summary": "Summary",
                    "five_minute_read": "Briefing",
                    "detailed_reading_note": "Detailed note",
                    "key_ideas": "- Key idea",
                    "detailed_outline": "## Outline\n- Point",
                    "important_examples": "- Example",
                    "actionable_takeaways": "- Action",
                    "notable_quotes": "- None captured verbatim.",
                    "best_for": "- Readers",
                    "consume_recommendation": "Open the source if needed.",
                    "why_it_matters": "Why it matters",
                    "open_questions": "- Question",
                    "topics": [],
                    "entities": [],
                    "concepts": [],
                },
            ),
        )

        raw_path = tmp_vault / "raw" / "videos" / "large-transcript.md"
        source_path = tmp_vault / "wiki" / "sources" / "videos" / "large-transcript.md"
        blob_path = tmp_vault / ".system" / "blobs" / "videos" / "large-transcript" / "primary.md"

        assert any(update.note_type == "evidence_blob" for update in updates)
        assert raw_path.exists()
        assert source_path.exists()
        assert blob_path.exists()

        raw_meta, raw_body = parse_frontmatter(raw_path.read_text(encoding="utf-8"))
        source_meta, source_body = parse_frontmatter(source_path.read_text(encoding="utf-8"))

        assert raw_meta["storage_tier"] == "warm"
        assert raw_meta["blob_storage_tier"] == "cold"
        assert raw_meta["blob_path"] == ".system/blobs/videos/large-transcript/primary.md"
        assert "Full preserved evidence blob" in raw_body
        assert "Preview truncated." in raw_body
        assert source_meta["raw_capture_path"] == "raw/videos/large-transcript.md"
        assert source_meta["raw_blob_path"] == ".system/blobs/videos/large-transcript/primary.md"
        assert "Full blob evidence" in source_body

    def test_existing_raw_capture_stays_backward_compatible_without_blob_upgrade(
        self,
        tmp_vault: Path,
    ):
        writer = VaultWriter(
            tmp_vault,
            storage_policy=EvidenceStoragePolicy(blob_threshold_bytes=10, blob_preview_chars=40),
        )
        raw_path = tmp_vault / "raw" / "articles" / "existing-evidence.md"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text("# Existing raw evidence\n", encoding="utf-8")

        item = SourceItem(
            url="https://example.com/existing-evidence",
            title="Existing Evidence",
            source_type=SourceType.ARTICLE,
        )
        content = SourceContent(
            source=item,
            raw_text="x" * 2000,
            cleaned_text="x" * 2000,
            archived_markdown="# Existing Evidence\n\n" + ("x" * 2000),
            raw_capture_kind="readable_article_markdown",
            extraction_quality="full",
            extraction_method="trafilatura",
            url_hash="existing-evidence",
        )

        update = writer.write_raw_capture(content, "existing-evidence")

        assert update.action == "unchanged"
        assert update.path == "raw/articles/existing-evidence.md"
        assert not (tmp_vault / ".system" / "blobs" / "articles" / "existing-evidence").exists()

    def test_update_topic_preserves_manual_sections(self, writer: VaultWriter):
        topic = Topic(name="Machine Learning", slug="machine-learning", summary="ML is cool")
        update = writer.write_topic(topic, ["Source A"])
        path = writer.vault_path / update.path
        original = path.read_text(encoding="utf-8")
        edited = original.replace(
            "_Patterns will be written here as repeated ideas emerge across sources._",
            "Manual pattern notes about recurring architecture tradeoffs.",
        )
        path.write_text(edited, encoding="utf-8")

        writer.write_topic(topic, ["Source B"])

        text = path.read_text(encoding="utf-8")
        assert "Manual pattern notes about recurring architecture tradeoffs." in text
        assert "[[Source A]]" in text
        assert "[[Source B]]" in text

    def test_update_topic_preserves_multiple_related_links(self, writer: VaultWriter):
        topic = Topic(
            name="Agents",
            slug="agents",
            summary="Agent systems",
            related_concepts=["Planning", "Tool Use"],
            related_entities=["OpenAI", "LangGraph"],
        )
        update = writer.write_topic(topic, ["Source A"])
        path = writer.vault_path / update.path

        writer.write_topic(
            Topic(
                name="Agents",
                slug="agents",
                summary="",
                related_concepts=["Memory"],
                related_entities=["Anthropic"],
            ),
            ["Source B"],
        )

        text = path.read_text(encoding="utf-8")
        assert "[[Planning]]" in text
        assert "[[Tool Use]]" in text
        assert "[[Memory]]" in text
        assert "[[OpenAI]]" in text
        assert "[[LangGraph]]" in text
        assert "[[Anthropic]]" in text

    def test_update_topic_replaces_placeholder_summary(self, writer: VaultWriter):
        topic = Topic(name="AI Safety", slug="ai-safety", summary="")
        update = writer.write_topic(topic, ["Source A"])
        path = writer.vault_path / update.path

        writer.write_topic(
            Topic(
                name="AI Safety",
                slug="ai-safety",
                summary="This topic tracks model risk, safeguards, and deployment tradeoffs.",
            ),
            ["Source B"],
        )

        text = path.read_text(encoding="utf-8")
        assert "This topic tracks model risk, safeguards, and deployment tradeoffs." in text
        assert "_This topic page will strengthen as more sources accumulate._" not in text
