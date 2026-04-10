"""Tests for the Phase 6 maintenance framework."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.automation.models import AutomationMode
from app.maintenance.planner import MaintenancePlanner
from app.maintenance.service import maintain_vault
from app.read_model.store import RELATION_DERIVED_FROM, ReadModelStore
from app.utils.markdown import build_frontmatter_doc, parse_frontmatter
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
        "artifact_neighborhood_refresh",
        "structural_repair",
        "hub_refresh",
        "backlink_repair",
        "read_model_refresh",
        "search_refresh",
    ]
    assert [task.task_name for task in deep.tasks] == [
        "artifact_neighborhood_refresh",
        "structural_repair",
        "hub_refresh",
        "backlink_repair",
        "candidate_synthesis_refresh",
        "read_model_refresh",
        "search_refresh",
    ]
    assert balanced.tasks[0].details["depth"] == 1
    assert deep.tasks[0].details["depth"] == 2


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
    topic_meta, _ = parse_frontmatter(topic_text)
    assert "Intro text that should survive maintenance." in topic_text
    assert "[[Agent Memory Systems]]" in topic_text
    assert "## Backlinks" in topic_text
    assert "## Maintenance Notes" in topic_text
    assert topic_meta["lifecycle"]["staleness_status"] == "current"
    assert topic_meta["lifecycle"]["last_confirmed_at"]
    assert topic_meta["lifecycle"]["reinforcement_count"] >= 1
    assert "wiki/indexes/INDEX.md" in result.changed_paths
    assert result.planned_tasks == [
        "artifact_neighborhood_refresh",
        "structural_repair",
        "hub_refresh",
        "backlink_repair",
        "read_model_refresh",
        "search_refresh",
    ]
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
    candidate_meta, _ = parse_frontmatter(candidate_text)
    assert "Candidate draft generated by deep maintenance." in candidate_text
    assert "Agent Memory Systems" in candidate_text
    assert candidate_meta["lifecycle"]["staleness_status"] == "needs_review"
    assert candidate_meta["lifecycle"]["last_confirmed_at"]
    assert candidate_meta["lifecycle"]["reinforcement_count"] == 2

    store = ReadModelStore(tmp_vault)
    store.refresh_paths(["wiki/synthesis/agent-memory-synthesis-candidate.md"])
    search_results = store.search_lexical("Agent Memory", limit=10)
    derived_edges = store.get_edges(
        from_note_path="wiki/synthesis/agent-memory-synthesis-candidate.md",
        relation_type=RELATION_DERIVED_FROM,
    )
    assert any("Agent Memory" in row["title"] for row in search_results)
    assert any(edge.target_title == "Agent Memory Systems" for edge in derived_edges)
    assert any(task.task_name == "read_model_refresh" for task in result.task_results)
    assert any(task.task_name == "search_refresh" for task in result.task_results)


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
    meta, _ = parse_frontmatter(text)
    assert meta["lifecycle"]["staleness_status"] == "current"
