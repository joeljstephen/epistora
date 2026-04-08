"""Append entries to the vault's operational logs."""

from __future__ import annotations

from pathlib import Path

from app.models.results import IngestResult, LintResult
from app.utils.dates import friendly_date
from app.vault import paths


def append_ingest_log(vault_path: Path, result: IngestResult) -> None:
    log_path = paths.ingest_log_path(vault_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    if not log_path.exists():
        log_path.write_text("# Ingest Log\n\nAppend-only log of all ingest operations.\n\n---\n\n")

    entry = f"""### {friendly_date(result.timestamp)}

- **Title:** {result.source_title or "unknown"}
- **URL:** {result.source_url}
- **Type:** {result.source_type}
- **Source note:** `{result.source_note_path}`
- **Raw capture:** `{result.raw_capture_path}`
- **Extraction:** `{result.extraction_method or "unknown"}`
  / `{result.extraction_quality or "unknown"}`
- **Tags:** {", ".join(result.bookmark_tags) or "none"}
- **Topics:** {", ".join(result.topics_updated) or "none"}
- **Entities:** {", ".join(result.entities_updated) or "none"}
- **Concepts:** {", ".join(result.concepts_updated) or "none"}
- **Deduplicated:** {"yes" if result.deduplicated else "no"}
"""
    if result.errors:
        entry += f"- **Errors:** {'; '.join(result.errors)}\n"
    entry += "\n---\n\n"

    with log_path.open("a", encoding="utf-8") as f:
        f.write(entry)


def write_lint_log(vault_path: Path, result: LintResult) -> str:
    log_path = paths.lint_log_path(vault_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Lint Report — {friendly_date(result.timestamp)}",
        "",
        f"- **Total notes scanned:** {result.total_notes}",
        f"- **Orphan pages:** {result.orphan_pages}",
        f"- **Missing backlinks:** {result.missing_backlinks}",
        f"- **Weak pages:** {result.weak_pages}",
        f"- **Issues found:** {len(result.issues)}",
        "",
        "---",
        "",
    ]

    for issue in result.issues:
        lines.append(f"### [{issue.severity.upper()}] {issue.category}")
        lines.append(f"- **File:** `{issue.file_path}`")
        lines.append(f"- **Message:** {issue.message}")
        if issue.suggestion:
            lines.append(f"- **Suggestion:** {issue.suggestion}")
        lines.append("")

    content = "\n".join(lines) + "\n"
    log_path.write_text(content, encoding="utf-8")
    return str(log_path.relative_to(vault_path))
