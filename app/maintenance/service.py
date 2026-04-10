"""Maintenance planner and executor."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from app.automation.models import AutomationMode
from app.compiler.lint_graph import _structural_lint
from app.maintenance.models import (
    MaintenanceClass,
    MaintenancePlan,
    MaintenanceResult,
    MaintenanceTask,
    MaintenanceTaskResult,
)
from app.maintenance.planner import MaintenancePlanner
from app.models.results import LintIssue
from app.read_model.store import (
    RELATION_SOURCE_CONCEPT,
    RELATION_SOURCE_ENTITY,
    RELATION_SOURCE_TOPIC,
    ReadModelStore,
)
from app.retrieval.indexer import VaultIndexer
from app.utils.dates import friendly_date, utcnow
from app.utils.markdown import build_frontmatter_doc, parse_markdown_file, wikilink
from app.vault.index_updater import rebuild_indexes
from app.vault.log_updater import write_maintenance_log
from app.vault.parser import VaultNote, scan_vault

logger = logging.getLogger(__name__)

_SECTION_RE = r"(?ms)^## {heading}\n.*?(?=^## |\Z)"
_SUMMARY_HEADINGS = (
    "## Short Summary",
    "## Concise Summary",
    "## Summary",
)
_SOURCE_RELATIONS_BY_TYPE = {
    "topic": RELATION_SOURCE_TOPIC,
    "entity": RELATION_SOURCE_ENTITY,
    "concept": RELATION_SOURCE_CONCEPT,
}


async def maintain_vault(
    *,
    vault_path: Path,
    mode: str = AutomationMode.SAFE,
    scope_paths: list[str] | None = None,
    force_rebuild: bool = False,
) -> MaintenanceResult:
    """Run a bounded maintenance plan for the vault."""
    planner = MaintenancePlanner(vault_path)
    plan = planner.plan(mode=mode, scope_paths=scope_paths, force_rebuild=force_rebuild)
    result = await _execute_plan(vault_path=vault_path, plan=plan)
    result.log_path = write_maintenance_log(vault_path, result)
    return result


async def _execute_plan(*, vault_path: Path, plan: MaintenancePlan) -> MaintenanceResult:
    result = MaintenanceResult(
        mode=plan.mode,
        scope_paths=plan.scope_paths,
        planned_tasks=[task.task_name for task in plan.tasks],
    )

    changed_paths: list[str] = []
    for task in plan.tasks:
        task_result = await _execute_task(
            vault_path=vault_path,
            task=task,
            aggregate_changed_paths=changed_paths,
        )
        result.task_results.append(task_result)
        changed_paths.extend(task_result.changed_paths)

    result.changed_paths = sorted(dict.fromkeys(changed_paths))
    return result


async def _execute_task(
    *,
    vault_path: Path,
    task: MaintenanceTask,
    aggregate_changed_paths: list[str],
) -> MaintenanceTaskResult:
    try:
        if task.task_name == "structural_audit":
            return await _run_structural_audit(vault_path, task)
        if task.task_name == "refresh_hub_pages":
            return _run_hub_refresh(vault_path, task)
        if task.task_name == "generate_synthesis_candidates":
            return _run_synthesis_candidates(vault_path, task)
        if task.task_name == "refresh_indexes":
            return _run_index_refresh(vault_path, task)
        if task.task_name == "refresh_read_model":
            return _run_read_model_refresh(vault_path, task, aggregate_changed_paths)
        if task.task_name == "refresh_search_index":
            return _run_search_refresh(vault_path, task)
        raise ValueError(f"Unknown maintenance task '{task.task_name}'")
    except Exception as exc:  # pragma: no cover - defensive isolation
        logger.error("Maintenance task failed (%s): %s", task.task_name, exc)
        return MaintenanceTaskResult(
            maintenance_class=task.maintenance_class,
            task_name=task.task_name,
            status="error",
            scope_paths=task.scope_paths,
            error=str(exc),
        )


async def _run_structural_audit(vault_path: Path, task: MaintenanceTask) -> MaintenanceTaskResult:
    notes = scan_vault(vault_path)
    state = {"vault_path": str(vault_path), "notes": notes}
    audit_result = await _structural_lint(state)
    issues: list[LintIssue] = audit_result.get("issues", [])
    issue_counts: dict[str, int] = {}
    for issue in issues:
        issue_counts[issue.category] = issue_counts.get(issue.category, 0) + 1

    return MaintenanceTaskResult(
        maintenance_class=MaintenanceClass.STRUCTURAL,
        task_name=task.task_name,
        scope_paths=task.scope_paths,
        details={
            "issues_found": len(issues),
            "issue_counts": issue_counts,
        },
    )


def _run_hub_refresh(vault_path: Path, task: MaintenanceTask) -> MaintenanceTaskResult:
    note_lookup = {
        note.rel_path: note
        for note in scan_vault(vault_path)
    }
    store = ReadModelStore(vault_path)
    changed_paths: list[str] = []
    attempted = 0

    for note_path in task.scope_paths:
        note = note_lookup.get(note_path)
        if note is None or note.note_type not in _SOURCE_RELATIONS_BY_TYPE:
            continue
        attempted += 1
        updated = _refresh_hub_note(vault_path, note, note_lookup, store)
        if updated:
            changed_paths.append(updated)
        if task.max_items and attempted >= task.max_items:
            break

    return MaintenanceTaskResult(
        maintenance_class=MaintenanceClass.SEMANTIC,
        task_name=task.task_name,
        scope_paths=task.scope_paths,
        changed_paths=sorted(dict.fromkeys(changed_paths)),
        details={"hubs_refreshed": len(changed_paths)},
    )


def _run_synthesis_candidates(vault_path: Path, task: MaintenanceTask) -> MaintenanceTaskResult:
    note_lookup = {
        note.rel_path: note
        for note in scan_vault(vault_path)
    }
    store = ReadModelStore(vault_path)
    changed_paths: list[str] = []

    topic_paths = task.scope_paths or [
        note.rel_path for note in note_lookup.values() if note.note_type == "topic"
    ]

    for topic_path in topic_paths:
        topic_note = note_lookup.get(topic_path)
        if topic_note is None:
            continue
        source_notes = _source_notes_for_hub(topic_note, note_lookup, store)
        if len(source_notes) < 2:
            continue
        synthesis_path = _candidate_synthesis_path(vault_path, topic_note)
        updated = _write_candidate_synthesis(synthesis_path, topic_note, source_notes)
        if updated:
            changed_paths.append(updated)
        if task.max_items and len(changed_paths) >= task.max_items:
            break

    return MaintenanceTaskResult(
        maintenance_class=MaintenanceClass.SYNTHESIS,
        task_name=task.task_name,
        scope_paths=task.scope_paths,
        changed_paths=sorted(dict.fromkeys(changed_paths)),
        details={"candidates_written": len(changed_paths)},
    )


def _run_index_refresh(vault_path: Path, task: MaintenanceTask) -> MaintenanceTaskResult:
    paths = rebuild_indexes(vault_path)
    return MaintenanceTaskResult(
        maintenance_class=MaintenanceClass.STRUCTURAL,
        task_name=task.task_name,
        scope_paths=task.scope_paths,
        changed_paths=sorted(dict.fromkeys(paths)),
        details={"indexes_updated": len(paths)},
    )


def _run_read_model_refresh(
    vault_path: Path,
    task: MaintenanceTask,
    aggregate_changed_paths: list[str],
) -> MaintenanceTaskResult:
    store = ReadModelStore(vault_path)
    strategy = task.details.get("strategy", "incremental")
    refresh_paths = sorted(
        {
            path
            for path in (aggregate_changed_paths + task.scope_paths)
            if path.endswith(".md")
        }
    )
    if strategy == "full" or not refresh_paths:
        details = store.rebuild()
        status = "full_rebuild"
    else:
        details = store.refresh_paths(refresh_paths)
        status = str(details.get("mode", "incremental"))

    return MaintenanceTaskResult(
        maintenance_class=MaintenanceClass.STORAGE,
        task_name=task.task_name,
        status=status,
        scope_paths=task.scope_paths,
        changed_paths=refresh_paths,
        details=details,
    )


def _run_search_refresh(vault_path: Path, task: MaintenanceTask) -> MaintenanceTaskResult:
    indexed_count = VaultIndexer(vault_path).rebuild()
    return MaintenanceTaskResult(
        maintenance_class=MaintenanceClass.STORAGE,
        task_name=task.task_name,
        scope_paths=task.scope_paths,
        details={"indexed_notes": indexed_count},
    )


def _refresh_hub_note(
    vault_path: Path,
    note: VaultNote,
    note_lookup: dict[str, VaultNote],
    store: ReadModelStore,
) -> str | None:
    source_notes = _source_notes_for_hub(note, note_lookup, store)
    backlinks = _backlink_titles(note, note_lookup, store)
    maintenance_notes = _maintenance_notes(note, source_notes, backlinks)

    path = vault_path / note.rel_path
    meta, body = parse_markdown_file(path)
    updated_body = body

    if note.note_type == "topic":
        updated_body = _replace_or_append_section(
            updated_body,
            "What I Have Saved",
            _render_bullets(note.title for note in source_notes),
        )
        updated_body = _replace_or_append_section(
            updated_body,
            "Related Concepts",
            _render_wikilinks(_aggregate_related(source_notes, "concepts", exclude=note.title)),
        )
        updated_body = _replace_or_append_section(
            updated_body,
            "Important Entities",
            _render_wikilinks(_aggregate_related(source_notes, "entities", exclude=note.title)),
        )
        updated_body = _replace_or_append_section(
            updated_body,
            "Recurring Patterns",
            _render_bullets(_summary_snippets(source_notes)),
        )
    elif note.note_type == "entity":
        updated_body = _replace_or_append_section(
            updated_body,
            "Mentioned In",
            _render_bullets(source.title for source in source_notes),
        )
        updated_body = _replace_or_append_section(
            updated_body,
            "Related Concepts",
            _render_wikilinks(_aggregate_related(source_notes, "concepts", exclude=note.title)),
        )
        updated_body = _replace_or_append_section(
            updated_body,
            "Why It Shows Up In My Vault",
            (
                f"Referenced in {len(source_notes)} source note"
                f"{'s' if len(source_notes) != 1 else ''}."
            ),
        )
    elif note.note_type == "concept":
        updated_body = _replace_or_append_section(
            updated_body,
            "Where It Appears",
            _render_bullets(source.title for source in source_notes),
        )
        updated_body = _replace_or_append_section(
            updated_body,
            "Related Concepts",
            _render_wikilinks(_aggregate_related(source_notes, "concepts", exclude=note.title)),
        )
        updated_body = _replace_or_append_section(
            updated_body,
            "Examples From Saved Sources",
            _render_bullets(_summary_snippets(source_notes)),
        )

    updated_body = _replace_or_append_section(
        updated_body,
        "Backlinks",
        _render_bullets(backlinks),
    )
    updated_body = _replace_or_append_section(
        updated_body,
        "Maintenance Notes",
        maintenance_notes,
    )

    meta["updated_at"] = friendly_date()
    meta["last_maintenance_at"] = utcnow().isoformat()
    meta["maintenance_classes"] = [MaintenanceClass.SEMANTIC.value]

    new_text = build_frontmatter_doc(meta, updated_body.strip())
    old_text = path.read_text(encoding="utf-8")
    if new_text == old_text:
        return None
    path.write_text(new_text, encoding="utf-8")
    return note.rel_path


def _source_notes_for_hub(
    note: VaultNote,
    note_lookup: dict[str, VaultNote],
    store: ReadModelStore,
) -> list[VaultNote]:
    relation_type = _SOURCE_RELATIONS_BY_TYPE.get(note.note_type)
    if not relation_type:
        return []
    source_paths = [
        edge.from_note_path
        for edge in store.get_edges(
            to_note_path=note.rel_path,
            relation_type=relation_type,
        )
        if edge.from_note_path
    ]
    return [note_lookup[path] for path in source_paths if path in note_lookup]


def _backlink_titles(
    note: VaultNote,
    note_lookup: dict[str, VaultNote],
    store: ReadModelStore,
) -> list[str]:
    titles: list[str] = []
    for edge in store.get_backlinks(note.rel_path):
        if not edge.from_note_path or edge.from_note_path not in note_lookup:
            continue
        titles.append(note_lookup[edge.from_note_path].title)
    return sorted(dict.fromkeys(titles))


def _aggregate_related(
    source_notes: list[VaultNote],
    field: str,
    *,
    exclude: str,
) -> list[str]:
    values: list[str] = []
    for source in source_notes:
        for value in source.meta.get(field, []) or []:
            if value and value != exclude:
                values.append(str(value))
    return sorted(dict.fromkeys(values))


def _summary_snippets(source_notes: list[VaultNote]) -> list[str]:
    snippets: list[str] = []
    for source in source_notes[:5]:
        snippet = _extract_summary_text(source.body)
        if snippet:
            snippets.append(f"{source.title}: {snippet}")
    return snippets or ["No multi-source pattern summary is available yet."]


def _extract_summary_text(body: str) -> str:
    for heading in _SUMMARY_HEADINGS:
        pattern = _SECTION_RE.format(heading=re.escape(heading[3:]))
        match = re.search(pattern, body)
        if match:
            section_text = re.sub(r"^## .+\n", "", match.group(0)).strip()
            if section_text:
                return " ".join(section_text.split())[:220]
    paragraphs = [chunk.strip() for chunk in body.split("\n\n") if chunk.strip()]
    for paragraph in paragraphs:
        if not paragraph.startswith("#"):
            return " ".join(paragraph.split())[:220]
    return ""


def _maintenance_notes(
    note: VaultNote,
    source_notes: list[VaultNote],
    backlinks: list[str],
) -> str:
    note_words = len(note.body.split())
    thin = note_words < 120 or len(source_notes) < 2
    lines = [
        f"- Last refreshed: {friendly_date()}",
        (
            f"- Supporting sources: {len(source_notes)}"
        ),
        f"- Backlinks: {len(backlinks)}",
        f"- Thin page: {'yes' if thin else 'no'}",
    ]
    if thin:
        lines.append(
            "- Recommendation: grow this page with more linked sources or a synthesis pass."
        )
    return "\n".join(lines)


def _candidate_synthesis_path(vault_path: Path, topic_note: VaultNote) -> Path:
    slug = topic_note.meta.get("slug", "") or topic_note.path.stem
    return vault_path / "wiki" / "synthesis" / f"{slug}-synthesis-candidate.md"


def _write_candidate_synthesis(
    path: Path,
    topic_note: VaultNote,
    source_notes: list[VaultNote],
) -> str | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "title": f"{topic_note.title} Synthesis Candidate",
        "type": "synthesis",
        "candidate": True,
        "generated_by": "maintenance_deep_mode",
        "candidate_topic": topic_note.title,
        "source_basis": [source.title for source in source_notes],
        "updated_at": friendly_date(),
    }
    patterns = _render_bullets(_summary_snippets(source_notes))
    basis = _render_bullets(source.title for source in source_notes)
    body = "\n\n".join(
        [
            f"# {topic_note.title} Synthesis Candidate",
            "> Candidate draft generated by deep maintenance.",
            "> Review before treating this as a durable synthesis note.",
            "## Candidate Scope",
            f"- Topic: {wikilink(topic_note.title)}\n- Supporting sources: {len(source_notes)}",
            "## Source Basis",
            basis,
            "## Cross-Source Patterns",
            patterns,
            "## Tensions / Gaps",
            "- Review the supporting sources for direct contradictions before promotion.",
            "## Promotion Checklist",
            "- Confirm durable claims against the source basis.\n"
            "- Replace candidate framing with durable synthesis wording.\n"
            "- Add any disagreements or gaps that should persist in the wiki.",
        ]
    )
    new_text = build_frontmatter_doc(meta, body)
    action = "created"
    if path.exists():
        old_text = path.read_text(encoding="utf-8")
        if old_text == new_text:
            return None
        action = "updated"
    path.write_text(new_text, encoding="utf-8")
    _ = action
    return str(path.relative_to(path.parents[2]))


def _replace_or_append_section(body: str, heading: str, content: str) -> str:
    normalized_content = content.strip() or "_None yet_"
    pattern = re.compile(_SECTION_RE.format(heading=re.escape(heading)))
    replacement = f"## {heading}\n\n{normalized_content}\n"
    if pattern.search(body):
        return pattern.sub(replacement, body).rstrip() + "\n"
    body = body.rstrip()
    if body:
        body += "\n\n"
    return body + replacement


def _render_bullets(items) -> str:
    values = [str(item).strip() for item in items if str(item).strip()]
    values = list(dict.fromkeys(values))
    if not values:
        return "- _None yet_"
    lines: list[str] = []
    for value in values:
        render_as_wikilink = (
            not value.startswith("[[")
            and "://" not in value
            and not value.startswith("_")
            and not value.endswith(".")
        )
        rendered = wikilink(value) if render_as_wikilink else value
        lines.append(f"- {rendered}")
    return "\n".join(lines)


def _render_wikilinks(items: list[str]) -> str:
    unique = list(dict.fromkeys(item for item in items if item))
    if not unique:
        return "_None yet_"
    return ", ".join(wikilink(item) for item in unique)
