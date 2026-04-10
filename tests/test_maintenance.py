"""Tests for the Phase 6 maintenance framework."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.automation.models import AutomationMode
from app.maintenance.planner import MaintenancePlanner
from app.maintenance.service import maintain_vault
from app.read_model.store import ReadModelStore
from app.retrieval.indexer import VaultIndexer
from app.utils.markdown import build_frontmatter_doc
from app.vault.paths import ensure_vault_dirs


def _write_note(path: Path, meta: dict, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_frontmatter_doc(meta, body), encoding="utf-8")


def _seed_vault(vault: Path) -> None:
    ensure_vault_dirs(vault)

    _write_note(
        vault / "wiki" / "sources" / "articles" / "agent-memory.md",
        {
            "title": "Agent Memory Systems",
            "type": "source",
            "source_url": "https://example.com/agent-memory",
            "source_type": "article",
            "topics": ["Agent Memory"],
            "entities": ["OpenAI"],
            "concepts": ["Long-Term Memory"],
            "raw_capture_path": "raw/articles/agent-memory.md",
            "extraction_quality": "full",
        },
        """# Agent Memory Systems

## Concise Summary

Agents need durable memory layers to improve over time.

## Related Notes

- **Topics:** [[Agent Memory]]
- **Entities:** [[OpenAI]]
- **Concepts:** [[Long-Term Memory]]
""",
    )
    _write_note(
        vault / "wiki" / "sources" / "articles" / "memory-planning.md",
        {
            "title": "Memory Planning",
            "type": "source",
            "source_url": "https://example.com/memory-planning",
            "source_type": "article",
            "topics": ["Agent Memory"],
            "entities": ["OpenAI"],
            "concepts": ["Long-Term Memory"],
            "raw_capture_path": "raw/articles/memory-planning.md",
            "extraction_quality": "full",
        },
        """# Memory Planning

## Summary

Planning quality improves when agents can retrieve prior work.

## Related Notes

- **Topics:** [[Agent Memory]]
- **Entities:** [[OpenAI]]
- **Concepts:** [[Long-Term Memory]]
""",
    )
    _write_note(
        vault / "wiki" / "topics" / "agent-memory.md",
        {"title": "Agent Memory", "type": "topic", "slug": "agent-memory"},
        """# Agent Memory

Intro text that should survive maintenance.

## Topic Summary

_This topic page will strengthen as more sources accumulate._

## What I Have Saved

- _No sources yet_
""",
    )
    _write_note(
        vault / "wiki" / "entities" / "companies" / "openai.md",
        {
            "title": "OpenAI",
            "type": "entity",
            "entity_type": "company",
            "slug": "openai",
        },
        """# OpenAI

## What It Is

_Company referenced in saved sources._
""",
    )
    _write_note(
        vault / "wiki" / "concepts" / "long-term-memory.md",
        {"title": "Long-Term Memory", "type": "concept", "slug": "long-term-memory"},
        """# Long-Term Memory

## Definition

_Definition will be refined as more sources mention this concept._
""",
    )
    _write_note(
        vault / "raw" / "articles" / "agent-memory.md",
        {"title": "Agent Memory Systems", "type": "raw"},
        "# raw capture",
    )
    _write_note(
        vault / "raw" / "articles" / "memory-planning.md",
        {"title": "Memory Planning", "type": "raw"},
        "# raw capture",
    )


def test_maintenance_planner_differs_between_balanced_and_deep(tmp_vault: Path):
    _seed_vault(tmp_vault)
    ReadModelStore(tmp_vault).rebuild()

    planner = MaintenancePlanner(tmp_vault)
    balanced = planner.plan(
        mode=AutomationMode.BALANCED,
        scope_paths=["wiki/sources/articles/agent-memory.md"],
    )
    deep = planner.plan(
        mode=AutomationMode.DEEP,
        scope_paths=["wiki/sources/articles/agent-memory.md"],
    )

    assert [task.task_name for task in balanced.tasks] == [
        "structural_audit",
        "refresh_hub_pages",
        "refresh_indexes",
        "refresh_read_model",
    ]
    assert [task.task_name for task in deep.tasks] == [
        "structural_audit",
        "refresh_hub_pages",
        "generate_synthesis_candidates",
        "refresh_indexes",
        "refresh_read_model",
        "refresh_search_index",
    ]


@pytest.mark.asyncio
async def test_balanced_maintenance_refreshes_hub_pages_and_indexes(tmp_vault: Path):
    _seed_vault(tmp_vault)
    ReadModelStore(tmp_vault).rebuild()

    result = await maintain_vault(
        vault_path=tmp_vault,
        mode=AutomationMode.BALANCED,
        scope_paths=["wiki/sources/articles/agent-memory.md"],
    )

    topic_text = (tmp_vault / "wiki" / "topics" / "agent-memory.md").read_text(encoding="utf-8")
    assert "Intro text that should survive maintenance." in topic_text
    assert "[[Agent Memory Systems]]" in topic_text
    assert "## Backlinks" in topic_text
    assert "## Maintenance Notes" in topic_text
    assert "wiki/indexes/INDEX.md" in result.changed_paths
    assert result.log_path == "wiki/logs/maintenance-log.md"


@pytest.mark.asyncio
async def test_deep_maintenance_creates_candidate_synthesis_and_refreshes_storage(tmp_vault: Path):
    _seed_vault(tmp_vault)
    ReadModelStore(tmp_vault).rebuild()

    result = await maintain_vault(
        vault_path=tmp_vault,
        mode=AutomationMode.DEEP,
        scope_paths=["wiki/sources/articles/agent-memory.md"],
    )

    candidate_path = tmp_vault / "wiki" / "synthesis" / "agent-memory-synthesis-candidate.md"
    assert candidate_path.exists()
    candidate_text = candidate_path.read_text(encoding="utf-8")
    assert "Candidate draft generated by deep maintenance." in candidate_text
    assert "Agent Memory Systems" in candidate_text

    search_results = VaultIndexer(tmp_vault).search("Agent Memory", limit=10)
    assert any("Agent Memory" in row["title"] for row in search_results)
    assert any(
        task.task_name == "refresh_search_index"
        for task in result.task_results
    )


@pytest.mark.asyncio
async def test_maintenance_does_not_corrupt_existing_note_frontmatter(tmp_vault: Path):
    _seed_vault(tmp_vault)
    ReadModelStore(tmp_vault).rebuild()

    await maintain_vault(
        vault_path=tmp_vault,
        mode=AutomationMode.BALANCED,
        scope_paths=["wiki/sources/articles/agent-memory.md"],
    )

    text = (tmp_vault / "wiki" / "entities" / "companies" / "openai.md").read_text(
        encoding="utf-8"
    )
    assert "title: OpenAI" in text
    assert "type: entity" in text
    assert "## Mentioned In" in text
