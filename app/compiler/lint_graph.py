"""LangGraph lint workflow — health-checks the vault."""

from __future__ import annotations

import json
import logging
from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.compiler.llm import get_llm
from app.compiler.prompts import LINT_ANALYSIS_PROMPT, SYSTEM_ROLE
from app.models.results import LintIssue, LintResult
from app.vault.log_updater import write_lint_log
from app.vault.parser import VaultNote, scan_vault

logger = logging.getLogger(__name__)


class LintState(TypedDict, total=False):
    vault_path: str
    notes: list[VaultNote]
    issues: list[LintIssue]
    result: LintResult


async def _scan_vault(state: LintState) -> LintState:
    from pathlib import Path

    vault_path = Path(state["vault_path"])
    notes = scan_vault(vault_path)
    return {**state, "notes": notes}


async def _structural_lint(state: LintState) -> LintState:
    """Rule-based structural checks: orphans, backlinks, weak pages."""
    notes: list[VaultNote] = state["notes"]
    issues: list[LintIssue] = []

    title_to_path: dict[str, str] = {}
    all_outgoing: dict[str, set[str]] = {}
    inbound: dict[str, set[str]] = {}

    for note in notes:
        title_to_path[note.title] = note.rel_path
        links = note.outgoing_links
        all_outgoing[note.rel_path] = set(links)
        for link in links:
            inbound.setdefault(link, set()).add(note.title)

    orphan_count = 0
    backlink_count = 0
    weak_count = 0

    for note in notes:
        if note.note_type in ("raw", "unknown"):
            continue

        if note.title not in inbound and note.note_type != "source":
            if "indexes" not in note.rel_path and "logs" not in note.rel_path:
                issues.append(
                    LintIssue(
                        severity="warning",
                        category="orphan_page",
                        message=f"'{note.title}' has no inbound links.",
                        file_path=note.rel_path,
                        suggestion="Link to this page from related notes or consider removing it.",
                    )
                )
                orphan_count += 1

    for note in notes:
        for link in note.outgoing_links:
            if link in title_to_path:
                linked_note = next((n for n in notes if n.title == link), None)
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
                    backlink_count += 1

    for note in notes:
        if note.note_type in ("topic", "entity", "concept"):
            source_count = len([link for link in inbound.get(note.title, set())])
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
                weak_count += 1

    mentioned_links: dict[str, int] = {}
    for note in notes:
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

    return {
        **state,
        "issues": issues,
        "_orphan_count": orphan_count,
        "_backlink_count": backlink_count,
        "_weak_count": weak_count,
    }


async def _llm_lint(state: LintState) -> LintState:
    """Use LLM to detect semantic issues like contradictions and duplicates."""
    notes: list[VaultNote] = state["notes"]
    issues: list[LintIssue] = state.get("issues", [])

    source_notes = [n for n in notes if n.note_type == "source"]
    if len(source_notes) < 2:
        return state

    vault_summary_parts = ["## Source Notes\n"]
    for n in source_notes[:30]:
        vault_summary_parts.append(f"- **{n.title}** (topics: {', '.join(n.topics)})")

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
        llm = get_llm()
        prompt = LINT_ANALYSIS_PROMPT.format(vault_summary=vault_summary)
        resp = await llm.ainvoke(
            [
                {"role": "system", "content": SYSTEM_ROLE},
                {"role": "user", "content": prompt},
            ]
        )
        raw = resp.content
        if isinstance(raw, str):
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"):
                    raw = raw[:-3]
            analysis = json.loads(raw)
        else:
            analysis = {}

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

    except Exception as e:
        logger.warning("LLM lint analysis failed: %s", e)

    return {**state, "issues": issues}


async def _generate_report(state: LintState) -> LintState:
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

    return {**state, "result": result}


def build_lint_graph() -> StateGraph:
    graph = StateGraph(LintState)

    graph.add_node("scan", _scan_vault)
    graph.add_node("structural", _structural_lint)
    graph.add_node("llm_lint", _llm_lint)
    graph.add_node("report", _generate_report)

    graph.set_entry_point("scan")
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
