"""Tests for the lint flow against intentionally broken fixture notes."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.models.knowledge import Entity, Topic
from app.vault.writer import VaultWriter


@pytest.fixture
def broken_vault(tmp_vault: Path) -> Path:
    """Create a vault with intentional issues for lint testing."""
    writer = VaultWriter(tmp_vault)

    from app.models.source import SourceContent, SourceItem, SourceType

    item = SourceItem(
        url="https://example.com/only-article",
        title="The Only Article",
        source_type=SourceType.ARTICLE,
    )
    content = SourceContent(
        source=item,
        raw_text="Raw",
        cleaned_text="Content about [[Nonexistent Page]] and [[Another Missing Page]].",
        word_count=5,
        extraction_quality="full",
        content_hash="h1",
        url_hash="u1",
    )
    writer.write_source_note(
        content=content,
        slug="the-only-article",
        raw_capture_path="raw/articles/the-only-article.md",
        summary="Test",
        five_minute_read="Briefing",
        detailed_reading_note="Detailed note",
        key_ideas="- test",
        detailed_outline="## test",
        important_examples="- claim",
        actionable_takeaways="- action",
        notable_quotes="- None captured verbatim.",
        best_for="- Readers",
        consume_recommendation="Read the original if needed.",
        why_it_matters="testing lint",
        open_questions="- none",
        topics=["Orphan Topic"],
        entities=[],
        concepts=[],
    )

    orphan_topic = Topic(name="Orphan Topic", slug="orphan-topic", summary="No one links here")
    writer.write_topic(orphan_topic, [])

    weak_entity = Entity(name="Lonely Entity", slug="lonely-entity", entity_type="tool")
    writer.write_entity(weak_entity, [])

    return tmp_vault


class TestStructuralLint:
    @pytest.mark.asyncio
    async def test_detects_orphan_pages(self, broken_vault: Path):
        from app.compiler.lint_graph import _structural_lint
        from app.vault.parser import scan_vault

        notes = scan_vault(broken_vault)
        state = {"vault_path": str(broken_vault), "notes": notes}
        result = await _structural_lint(state)
        issues = result["issues"]
        orphan_issues = [i for i in issues if i.category == "orphan_page"]
        assert len(orphan_issues) > 0

    @pytest.mark.asyncio
    async def test_detects_weak_pages(self, broken_vault: Path):
        from app.compiler.lint_graph import _structural_lint
        from app.vault.parser import scan_vault

        notes = scan_vault(broken_vault)
        state = {"vault_path": str(broken_vault), "notes": notes}
        result = await _structural_lint(state)
        issues = result["issues"]
        weak_issues = [i for i in issues if i.category == "weak_page"]
        assert len(weak_issues) > 0

    @pytest.mark.asyncio
    async def test_detects_missing_pages(self, broken_vault: Path):
        from app.compiler.lint_graph import _structural_lint
        from app.vault.parser import scan_vault

        notes = scan_vault(broken_vault)
        state = {"vault_path": str(broken_vault), "notes": notes}
        result = await _structural_lint(state)
        issues = result["issues"]
        categories = [i.category for i in issues]
        assert "weak_page" in categories or "orphan_page" in categories


class TestLintReport:
    @pytest.mark.asyncio
    async def test_generates_report(self, broken_vault: Path):
        from app.compiler.lint_graph import _generate_report, _structural_lint
        from app.vault.parser import scan_vault

        notes = scan_vault(broken_vault)
        state = {"vault_path": str(broken_vault), "notes": notes}
        state = {**state, **await _structural_lint(state)}
        state = {**state, **await _generate_report(state)}

        result = state["result"]
        assert result.total_notes > 0
        assert result.report_path
        report_file = broken_vault / result.report_path
        assert report_file.exists()
