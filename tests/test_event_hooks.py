"""Tests for internal event hooks."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.automation.models import AutomationMode
from app.events import EventType, clear_subscribers, subscribe
from app.maintenance.service import maintain_vault
from app.models.knowledge import Topic
from app.read_model.store import ReadModelStore
from app.services.query_service import _maybe_save
from app.utils.markdown import build_frontmatter_doc
from app.vault.paths import ensure_vault_dirs
from app.vault.writer import VaultWriter


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
        vault / "wiki" / "topics" / "agent-memory.md",
        {"title": "Agent Memory", "type": "topic", "slug": "agent-memory"},
        """# Agent Memory

## Topic Summary

_This topic page will strengthen as more sources accumulate._
""",
    )
    _write_note(
        vault / "raw" / "articles" / "agent-memory.md",
        {"title": "Agent Memory Systems", "type": "raw"},
        "# raw capture",
    )


@pytest.fixture(autouse=True)
def _reset_event_subscribers():
    clear_subscribers()
    yield
    clear_subscribers()


def test_artifact_written_event_emitted_for_vault_writes(tmp_vault: Path):
    events = []
    subscribe(EventType.ARTIFACT_WRITTEN, events.append)

    writer = VaultWriter(tmp_vault)
    update = writer.write_topic(
        topic=Topic(name="Maintenance", slug="maintenance", summary="Topic summary"),
        source_titles=["Source A"],
    )

    assert update.path == "wiki/topics/maintenance.md"
    assert len(events) == 1
    assert events[0].event_type == "artifact_written"
    assert events[0].payload["path"] == "wiki/topics/maintenance.md"
    assert events[0].payload["note_type"] == "topic"


@pytest.mark.asyncio
async def test_maintenance_completed_event_emitted(tmp_vault: Path):
    events = []
    subscribe(EventType.MAINTENANCE_COMPLETED, events.append)

    _seed_vault(tmp_vault)
    ReadModelStore(tmp_vault).rebuild()

    await maintain_vault(
        vault_path=tmp_vault,
        mode=AutomationMode.BALANCED,
        scope_paths=["wiki/sources/articles/agent-memory.md"],
    )

    assert len(events) == 1
    assert events[0].event_type == "maintenance_completed"
    assert "structural_repair" in events[0].payload["planned_tasks"]
    assert events[0].payload["log_path"] == "wiki/logs/maintenance-log.md"


@pytest.mark.asyncio
async def test_run_maintenance_emits_scheduled_tick(tmp_vault: Path):
    from app.automation.runner import run_maintenance

    events = []
    subscribe(EventType.SCHEDULED_MAINTENANCE_TICK, events.append)

    with (
        patch("app.automation.runner.get_settings") as mock_settings,
        patch("app.automation.runner.maintain_vault", new_callable=AsyncMock) as mock_maintain,
    ):
        mock_settings.return_value.automation_default_mode = "balanced"
        mock_settings.return_value.automation_run_lint = False
        mock_settings.return_value.automation_run_rebuild_indexes = False
        mock_settings.return_value.vault_path = tmp_vault
        mock_maintain.return_value = MagicMock()
        mock_maintain.return_value.task_results = []
        mock_maintain.return_value.model_dump.return_value = {
            "mode": "balanced",
            "planned_tasks": ["structural_repair"],
            "task_results": [],
            "changed_paths": [],
            "log_path": "wiki/logs/maintenance-log.md",
        }

        await run_maintenance(scope_paths=["wiki/sources/articles/agent-memory.md"])

    assert len(events) == 1
    assert events[0].event_type == "scheduled_maintenance_tick"
    assert events[0].payload["mode"] == "balanced"
    assert events[0].payload["scope_paths"] == ["wiki/sources/articles/agent-memory.md"]


def test_query_answer_saved_event_emitted(tmp_vault: Path):
    events = []
    subscribe(EventType.QUERY_ANSWER_SAVED, events.append)

    saved_to = _maybe_save(
        vault_path=tmp_vault,
        question="What changed in maintenance?",
        answer="## Direct Findings\n- Structural repair now owns index rebuilds.",
        references=["wiki/topics/maintenance.md"],
        save_synthesis=True,
    )

    assert saved_to == "outputs/answers/what-changed-in-maintenance.md"
    assert len(events) == 1
    assert events[0].event_type == "query_answer_saved"
    assert events[0].payload["saved_to"] == saved_to
    assert events[0].payload["source_references"] == ["wiki/topics/maintenance.md"]
