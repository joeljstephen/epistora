"""Tests for agent-first navigation files and vault structure."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.models.knowledge import Topic
from app.vault.index_updater import rebuild_indexes
from app.vault.writer import VaultWriter


@pytest.fixture
def populated_vault(tmp_vault: Path) -> Path:
    writer = VaultWriter(tmp_vault)

    from app.models.source import SourceContent, SourceItem, SourceType

    for i, (title, url) in enumerate(
        [
            ("AI Agents Overview", "https://example.com/ai-agents"),
            ("LangChain Guide", "https://example.com/langchain"),
        ]
    ):
        item = SourceItem(url=url, title=title, source_type=SourceType.ARTICLE)
        content = SourceContent(
            source=item,
            raw_text=f"Raw content for {title}",
            cleaned_text=f"Detailed content about {title}.",
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
            detailed_reading_note=f"Reading note for {title}",
            key_ideas=f"- Key point about {title}",
            detailed_outline=f"## Overview of {title}",
            important_examples=f"- Example from {title}",
            actionable_takeaways=f"- Apply ideas from {title}",
            notable_quotes="- None captured verbatim.",
            best_for=f"- Readers learning about {title}",
            consume_recommendation=f"Read {title} for more.",
            why_it_matters=f"{title} is important",
            open_questions=f"- Questions about {title}",
            topics=["AI"],
            entities=["LangChain"],
            concepts=["AI Agents"],
        )

    topic = Topic(name="AI", slug="ai", summary="Artificial Intelligence")
    writer.write_topic(topic, ["AI Agents Overview", "LangChain Guide"])

    rebuild_indexes(tmp_vault)
    return tmp_vault


class TestStartHereFile:
    def test_start_here_exists_after_rebuild(self, populated_vault: Path):
        start_here = populated_vault / "wiki" / "indexes" / "START_HERE.md"
        assert start_here.exists()

    def test_start_here_contains_orientation(self, populated_vault: Path):
        start_here = populated_vault / "wiki" / "indexes" / "START_HERE.md"
        content = start_here.read_text()
        assert "Vault Layers" in content
        assert "raw/" in content
        assert "wiki/" in content
        assert "outputs/" in content

    def test_start_here_contains_stats(self, populated_vault: Path):
        start_here = populated_vault / "wiki" / "indexes" / "START_HERE.md"
        content = start_here.read_text()
        assert "source notes" in content
        assert "topic pages" in content

    def test_start_here_contains_routing(self, populated_vault: Path):
        start_here = populated_vault / "wiki" / "indexes" / "START_HERE.md"
        content = start_here.read_text()
        assert "Topic overview" in content or "topic" in content.lower()
        assert "Entity profile" in content or "entity" in content.lower()


class TestQueryProtocolFile:
    def test_query_protocol_exists_after_rebuild(self, populated_vault: Path):
        qp = populated_vault / "wiki" / "indexes" / "QUERY_PROTOCOL.md"
        assert qp.exists()

    def test_query_protocol_contains_steps(self, populated_vault: Path):
        qp = populated_vault / "wiki" / "indexes" / "QUERY_PROTOCOL.md"
        content = qp.read_text()
        assert "Step 1" in content or "Orient" in content
        assert "Answer Rules" in content or "Answer" in content
        assert "Evidence Trust" in content or "trust" in content.lower()

    def test_query_protocol_mentions_answer_structure(self, populated_vault: Path):
        qp = populated_vault / "wiki" / "indexes" / "QUERY_PROTOCOL.md"
        content = qp.read_text()
        assert "Direct Findings" in content
        assert "Cross-Source Synthesis" in content
        assert "Gaps" in content


class TestAgentsMd:
    def test_agents_md_in_template(self):
        template_agents = Path(__file__).parent.parent / "knowledge_vault_template" / "AGENTS.md"
        assert template_agents.exists()

    def test_agents_md_contains_navigation_sequence(self):
        template_agents = Path(__file__).parent.parent / "knowledge_vault_template" / "AGENTS.md"
        content = template_agents.read_text()
        assert "Navigation Sequence" in content or "Agent Navigation" in content
        assert "Step 1" in content or "Orient" in content
        assert "raw/" in content
        assert "wiki/" in content

    def test_agents_md_contains_answer_structure(self):
        template_agents = Path(__file__).parent.parent / "knowledge_vault_template" / "AGENTS.md"
        content = template_agents.read_text()
        assert "Direct Findings" in content
        assert "Cross-Source Synthesis" in content
        assert "Relevant Notes" in content

    def test_agents_md_mentions_extraction_quality(self):
        template_agents = Path(__file__).parent.parent / "knowledge_vault_template" / "AGENTS.md"
        content = template_agents.read_text()
        assert "extraction_quality" in content


class TestIndexRebuildGeneratesNavigation:
    def test_rebuild_generates_reader_and_navigation_index_files(self, populated_vault: Path):
        index_dir = populated_vault / "wiki" / "indexes"
        expected = [
            "INDEX.md",
            "TOPICS.md",
            "ENTITIES.md",
            "CONCEPTS.md",
            "READING_HOME.md",
            "VIDEOS.md",
            "ARTICLES.md",
            "TOPICS_FEED.md",
            "START_HERE.md",
            "QUERY_PROTOCOL.md",
        ]
        for name in expected:
            assert (index_dir / name).exists(), f"{name} should exist after rebuild"

    def test_rebuild_returns_all_six_paths(self, populated_vault: Path):
        updated = rebuild_indexes(populated_vault)
        expected_names = {
            "INDEX.md",
            "TOPICS.md",
            "ENTITIES.md",
            "CONCEPTS.md",
            "READING_HOME.md",
            "VIDEOS.md",
            "ARTICLES.md",
            "TOPICS_FEED.md",
            "START_HERE.md",
            "QUERY_PROTOCOL.md",
            "DASHBOARD.md",
        }
        updated_names = {Path(p).name for p in updated}
        assert expected_names == updated_names

    def test_reading_home_is_item_centric(self, populated_vault: Path):
        content = (populated_vault / "wiki" / "indexes" / "READING_HOME.md").read_text()
        assert "What To Look At Next" in content
        assert "Best next action" in content

    def test_reader_views_include_obsidian_dataview_layer(self, populated_vault: Path):
        content = (populated_vault / "wiki" / "indexes" / "READING_HOME.md").read_text()
        assert "## Obsidian Enhanced View" in content
        assert "```dataviewjs" in content
        assert "epistora-reader-grid" in content

    def test_topics_feed_is_topic_centric(self, populated_vault: Path):
        content = (populated_vault / "wiki" / "indexes" / "TOPICS_FEED.md").read_text()
        assert "Active Topic Clusters" in content
        assert "Theme Watchlist" in content

    def test_rebuild_writes_obsidian_reader_snippet(self, populated_vault: Path):
        snippet = populated_vault / ".obsidian" / "snippets" / "epistora-reader-views.css"
        assert snippet.exists()
        css = snippet.read_text()
        assert ".epistora-reader-grid" in css
        assert ".epistora-reader-card" in css


class TestSkillFiles:
    def test_claude_code_skill_exists(self):
        skill_path = Path(__file__).parent.parent / ".claude" / "skills" / "vault-query.md"
        assert skill_path.exists()

    def test_claude_code_skill_contains_procedure(self):
        skill_path = Path(__file__).parent.parent / ".claude" / "skills" / "vault-query.md"
        content = skill_path.read_text()
        assert "Orient" in content
        assert "AGENTS.md" in content
        assert "START_HERE" in content
        assert "Direct Findings" in content

    def test_opencode_instructions_exist(self):
        opencode_path = Path(__file__).parent.parent / ".opencode" / "VAULT_QUERY.md"
        assert opencode_path.exists()

    def test_opencode_instructions_contain_procedure(self):
        opencode_path = Path(__file__).parent.parent / ".opencode" / "VAULT_QUERY.md"
        content = opencode_path.read_text()
        assert "AGENTS.md" in content
        assert "START_HERE" in content
        assert "Direct Findings" in content
