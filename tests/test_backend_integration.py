"""Integration tests: services run end-to-end with a mocked backend router."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.backends.models import BackendResponse, BackendType
from app.compiler.llm import reset_backend_router


@pytest.fixture(autouse=True)
def _reset_router():
    """Ensure each test gets a fresh router."""
    reset_backend_router()
    yield
    reset_backend_router()


def _mock_generate_structured(response_json: dict):
    """Create a mock for router.generate_structured that returns the given JSON."""

    async def _mock(request, schema_class=None):
        return BackendResponse(
            text=json.dumps(response_json),
            success=True,
            backend_used=BackendType.API,
            model_used="test-model",
        )

    return _mock


def _mock_generate_text(text: str):
    """Create a mock for router.generate that returns the given text."""

    async def _mock(request):
        return BackendResponse(
            text=text,
            success=True,
            backend_used=BackendType.API,
            model_used="test-model",
        )

    return _mock


class TestIngestServiceWithMockedBackend:
    @pytest.mark.asyncio
    async def test_analyse_content_uses_router(self, tmp_path: Path):
        """The ingest graph _analyse_content node calls run_structured correctly."""
        from app.compiler.ingest_graph import IngestState, _analyse_content
        from app.models.source import SourceContent, SourceItem, SourceType

        item = SourceItem(
            url="https://example.com/test",
            title="Test Article",
            source_type=SourceType.ARTICLE,
        )
        content = SourceContent(
            source=item,
            raw_text="raw",
            cleaned_text="This is a test article about AI.",
            extraction_quality="full",
        )
        state: IngestState = {"item": item, "content": content, "slug": "test-article"}

        analysis = {
            "summary": "Test summary",
            "five_minute_read": "Briefing",
            "detailed_reading_note": "Detailed note",
            "key_ideas": "- Point 1",
            "detailed_outline": "## Outline",
            "important_examples": "- Claim",
            "actionable_takeaways": "- Action",
            "notable_quotes": "- None captured verbatim.",
            "best_for": "- Readers",
            "consume_recommendation": "Read the original for more detail.",
            "why_it_matters": "It matters.",
            "open_questions": "- Question",
            "topics": ["AI"],
            "entities": [{"name": "OpenAI", "type": "company", "description": "AI lab"}],
            "concepts": [{"name": "LLM", "definition": "Large Language Model"}],
        }

        with patch(
            "app.compiler.ingest_graph.run_structured",
            new_callable=AsyncMock,
            return_value=BackendResponse(
                text=json.dumps(analysis),
                success=True,
                backend_used=BackendType.API,
                model_used="test-model",
            ),
        ):
            result = await _analyse_content(state)

        assert result["analysis"]["summary"] == "Test summary"
        assert result["analysis"]["topics"] == ["AI"]


class TestQueryServiceWithMockedBackend:
    @pytest.mark.asyncio
    async def test_generate_answer_uses_router(self, tmp_path: Path):
        """The query graph _generate_answer node calls run_text correctly."""
        from app.compiler.query_graph import QueryState, _generate_answer

        state: QueryState = {
            "question": "What is AI?",
            "vault_path": str(tmp_path),
            "relevant_notes": [{"title": "AI Note", "snippet": "AI is...", "type": "source"}],
            "context": "### AI Note\nAI is...",
        }

        with patch(
            "app.compiler.query_graph.run_text",
            new_callable=AsyncMock,
            return_value=BackendResponse(
                text="AI stands for Artificial Intelligence.",
                success=True,
                backend_used=BackendType.API,
                model_used="test-model",
            ),
        ):
            result = await _generate_answer(state)

        assert "Artificial Intelligence" in result["answer"]


class TestLintServiceWithMockedBackend:
    @pytest.mark.asyncio
    async def test_llm_lint_uses_router(self, tmp_vault: Path):
        """The lint graph _llm_lint node calls run_structured correctly."""
        from app.compiler.lint_graph import LintState, _llm_lint
        from app.vault.parser import VaultNote

        # Create real vault note files so VaultNote can parse them
        for i in range(3):
            note_dir = tmp_vault / "wiki" / "sources" / "articles"
            note_dir.mkdir(parents=True, exist_ok=True)
            note_path = note_dir / f"note-{i}.md"
            note_path.write_text(
                f"---\ntitle: Note {i}\ntype: source\n"
                f"topics:\n  - AI\n---\n\nContent of note {i}.\n",
                encoding="utf-8",
            )

        notes = [
            VaultNote(tmp_vault / "wiki" / "sources" / "articles" / f"note-{i}.md", tmp_vault)
            for i in range(3)
        ]

        state: LintState = {
            "vault_path": str(tmp_vault),
            "notes": notes,
            "issues": [],
        }

        lint_analysis = {
            "duplicate_candidates": [],
            "potential_contradictions": [],
            "missing_pages": [{"name": "GPT", "mention_count": 3, "type": "concept"}],
            "merge_candidates": [],
        }

        with patch(
            "app.compiler.lint_graph.run_structured",
            new_callable=AsyncMock,
            return_value=BackendResponse(
                text=json.dumps(lint_analysis),
                success=True,
                backend_used=BackendType.OPENCODE,
                model_used="test-model",
            ),
        ):
            result = await _llm_lint(state)

        missing_page_issues = [i for i in result["issues"] if i.category == "missing_page"]
        assert any("GPT" in i.message for i in missing_page_issues)
