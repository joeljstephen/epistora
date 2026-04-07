"""Tests for vault writing operations."""

from pathlib import Path

import pytest

from app.models.knowledge import Concept, Entity, Topic
from app.models.source import SourceContent, SourceItem, SourceType
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
        extraction_quality="good",
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
            summary="A test summary",
            key_takeaways="- Key point 1\n- Key point 2",
            detailed_outline="## Section 1\n- Detail",
            important_claims="- Claim A",
            why_matters="This matters because testing.",
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
        assert update.action == "updated"

    def test_update_topic_preserves_manual_sections(self, writer: VaultWriter):
        topic = Topic(name="Machine Learning", slug="machine-learning", summary="ML is cool")
        update = writer.write_topic(topic, ["Source A"])
        path = writer.vault_path / update.path
        original = path.read_text(encoding="utf-8")
        edited = original.replace(
            "_Patterns will emerge as more sources are ingested on this topic._",
            "Manual pattern notes about recurring architecture tradeoffs.",
        )
        path.write_text(edited, encoding="utf-8")

        writer.write_topic(topic, ["Source B"])

        text = path.read_text(encoding="utf-8")
        assert "Manual pattern notes about recurring architecture tradeoffs." in text
        assert "[[Source A]]" in text
        assert "[[Source B]]" in text
