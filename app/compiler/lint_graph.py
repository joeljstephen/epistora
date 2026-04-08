"""LangGraph lint workflow — health-checks the vault."""

from __future__ import annotations

import json
import logging
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.backends.models import TaskName
from app.compiler.llm import run_structured
from app.compiler.prompts import (
    LINT_ANALYSIS_JSON_SCHEMA,
    LINT_ANALYSIS_PROMPT,
    SYSTEM_ROLE,
)
from app.models.results import LintIssue, LintResult
from app.vault.log_updater import write_lint_log
from app.vault.parser import VaultNote, scan_vault

logger = logging.getLogger(__name__)

LINTABLE_NOTE_TYPES = {"source", "topic", "entity", "concept", "synthesis"}


class LintState(TypedDict, total=False):
    vault_path: str
    notes: list[VaultNote]
    issues: list[LintIssue]
    result: LintResult


async def _scan_vault(state: LintState) -> dict:
    from pathlib import Path

    vault_path = Path(state["vault_path"])
    notes = scan_vault(vault_path)
    return {"notes": notes}


async def _structural_lint(state: LintState) -> dict:
    """Rule-based structural checks: orphans, backlinks, weak pages."""
    from pathlib import Path

    vault_path = Path(state["vault_path"])
    notes: list[VaultNote] = state["notes"]
    issues: list[LintIssue] = []

    title_to_path: dict[str, str] = {}
    inbound: dict[str, set[str]] = {}

    lintable_notes = [note for note in notes if note.note_type in LINTABLE_NOTE_TYPES]

    for note in lintable_notes:
        title_to_path[note.title] = note.rel_path
        for link in note.outgoing_links:
            inbound.setdefault(link, set()).add(note.title)

    for note in lintable_notes:
        if note.note_type == "source":
            raw_capture_path = note.meta.get("raw_capture_path", "")
            if not raw_capture_path:
                issues.append(
                    LintIssue(
                        severity="warning",
                        category="missing_raw_capture",
                        message=f"'{note.title}' has no raw capture link in frontmatter.",
                        file_path=note.rel_path,
                        suggestion="Source notes should point back to their immutable raw archive.",
                    )
                )
            elif not (vault_path / raw_capture_path).exists():
                issues.append(
                    LintIssue(
                        severity="warning",
                        category="missing_raw_capture",
                        message=(
                            f"'{note.title}' points to a missing raw capture: "
                            f"{raw_capture_path}."
                        ),
                        file_path=note.rel_path,
                        suggestion="Recreate the raw capture or re-run ingest for this source.",
                    )
                )

        if note.title not in inbound and note.note_type != "source":
            issues.append(
                LintIssue(
                    severity="warning",
                    category="orphan_page",
                    message=f"'{note.title}' has no inbound links.",
                    file_path=note.rel_path,
                    suggestion="Link to this page from related notes or consider removing it.",
                )
            )

    for note in lintable_notes:
        for link in note.outgoing_links:
            if link not in title_to_path:
                continue
            linked_note = next((n for n in lintable_notes if n.title == link), None)
            if linked_note and note.title not in linked_note.outgoing_links:
                if note.note_type == "source" and linked_note.note_type in (
                    "topic",
                    "entity",
                    "concept",
                ):
                    continue
                issues.append(
                    LintIssue(
                        severity="info",
                        category="missing_backlink",
                        message=f"'{note.title}' links to '{link}' but no backlink exists.",
                        file_path=note.rel_path,
                        suggestion=f"Add a reference to [[{note.title}]] in '{link}'.",
                    )
                )

    for note in lintable_notes:
        if note.note_type in ("topic", "entity", "concept"):
            source_count = len(inbound.get(note.title, set()))
            if source_count < 2:
                message = (
                    f"'{note.title}' ({note.note_type}) has only "
                    f"{source_count} source reference(s)."
                )
                issues.append(
                    LintIssue(
                        severity="info",
                        category="weak_page",
                        message=message,
                        file_path=note.rel_path,
                        suggestion="This page will strengthen as more sources are ingested.",
                    )
                )

    mentioned_links: dict[str, int] = {}
    for note in lintable_notes:
        for link in note.outgoing_links:
            if link not in title_to_path:
                mentioned_links[link] = mentioned_links.get(link, 0) + 1
    for name, count in mentioned_links.items():
        if count >= 2:
            issues.append(
                LintIssue(
                    severity="warning",
                    category="missing_page",
                    message=f"'{name}' is referenced {count} times but has no page.",
                    file_path="",
                    suggestion=f"Consider creating a page for '{name}'.",
                )
            )

    return {"issues": issues}


async def _llm_lint(state: LintState) -> dict:
    """Use LLM to detect semantic issues like contradictions and duplicates."""
    notes: list[VaultNote] = state["notes"]
    issues: list[LintIssue] = state.get("issues", [])

    source_notes = [n for n in notes if n.note_type == "source"]
    if len(source_notes) < 2:
        return {}

    vault_summary_parts = ["## Source Notes\n"]
    for n in source_notes[:30]:
        vault_summary_parts.append(
            "- **"
            + n.title
            + "** "
            + f"(topics: {', '.join(n.topics)}, "
            + f"quality: {n.meta.get('extraction_quality', 'unknown')})"
        )

    topic_notes = [n for n in notes if n.note_type == "topic"]
    if topic_notes:
        vault_summary_parts.append("\n## Topic Pages\n")
        for n in topic_notes:
            vault_summary_parts.append(f"- {n.title}")

    entity_notes = [n for n in notes if n.note_type == "entity"]
    if entity_notes:
        vault_summary_parts.append("\n## Entity Pages\n")
        for n in entity_notes:
            vault_summary_parts.append(f"- {n.title}")

    vault_summary = "\n".join(vault_summary_parts)

    try:
        prompt = LINT_ANALYSIS_PROMPT.format(vault_summary=vault_summary)
        resp = await run_structured(
            task=TaskName.LINT,
            system_prompt=SYSTEM_ROLE,
            user_prompt=prompt,
            json_schema_hint=LINT_ANALYSIS_JSON_SCHEMA,
        )
        if resp.success:
            analysis = json.loads(resp.text)
            logger.info(
                "Lint analysis via %s (model=%s, fallback=%s)",
                resp.backend_used,
                resp.model_used,
                resp.was_fallback,
            )
        else:
            raise RuntimeError(resp.error)

        for dup in analysis.get("duplicate_candidates", []):
            issues.append(
                LintIssue(
                    severity="warning",
                    category="potential_duplicate",
                    message=f"Possible duplicates: {', '.join(dup.get('notes', []))}",
                    suggestion=dup.get("reason", ""),
                )
            )

        for contradiction in analysis.get("potential_contradictions", []):
            notes_label = ", ".join(contradiction.get("notes", []))
            tension = contradiction.get("tension", "")
            issues.append(
                LintIssue(
                    severity="error",
                    category="contradiction",
                    message=f"Contradiction between {notes_label}: {tension}",
                    suggestion="Review both sources and update or flag in Open Questions.",
                )
            )

        for missing in analysis.get("missing_pages", []):
            name = missing.get("name", "")
            already_flagged = any(
                i.message and name in i.message for i in issues if i.category == "missing_page"
            )
            if not already_flagged:
                issues.append(
                    LintIssue(
                        severity="info",
                        category="missing_page",
                        message=f"'{name}' appears frequently but has no dedicated page.",
                        suggestion=f"Create a {missing.get('type', 'concept')} page for '{name}'.",
                    )
                )

        for gap in analysis.get("navigation_gaps", []):
            notes_label = ", ".join(gap.get("notes", []))
            issues.append(
                LintIssue(
                    severity="info",
                    category="navigation_gap",
                    message=(
                        f"Navigation gap around {notes_label or 'related notes'}: "
                        f"{gap.get('reason', '')}"
                    ),
                    suggestion="Improve backlinks, index entries, or topic/source cross-links.",
                )
            )

    except Exception as e:
        logger.warning("LLM lint analysis failed: %s", e)

    return {"issues": issues}


async def _generate_report(state: LintState) -> dict:
    from pathlib import Path

    vault_path = Path(state["vault_path"])
    notes: list[VaultNote] = state["notes"]
    issues: list[LintIssue] = state.get("issues", [])

    orphans = sum(1 for i in issues if i.category == "orphan_page")
    backlinks = sum(1 for i in issues if i.category == "missing_backlink")
    weak = sum(1 for i in issues if i.category == "weak_page")

    result = LintResult(
        issues=issues,
        total_notes=len(notes),
        orphan_pages=orphans,
        missing_backlinks=backlinks,
        weak_pages=weak,
    )

    report_path = write_lint_log(vault_path, result)
    result.report_path = report_path

    return {"result": result}


def build_lint_graph() -> StateGraph:
    graph = StateGraph(LintState)

    graph.add_node("scan", _scan_vault)
    graph.add_node("structural", _structural_lint)
    graph.add_node("llm_lint", _llm_lint)
    graph.add_node("report", _generate_report)

    graph.add_edge(START, "scan")
    graph.add_edge("scan", "structural")
    graph.add_edge("structural", "llm_lint")
    graph.add_edge("llm_lint", "report")
    graph.add_edge("report", END)

    return graph


_compiled_graph = None


def get_lint_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_lint_graph().compile()
    return _compiled_graph
