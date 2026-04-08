"""Rebuild and update vault index files."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from app.utils.dates import friendly_date
from app.utils.markdown import path_wikilink, wikilink
from app.vault import paths
from app.vault.parser import VaultNote, scan_vault


def rebuild_indexes(vault_path: Path) -> list[str]:
    notes = scan_vault(vault_path)
    updated: list[str] = []

    updated.append(_write_main_index(vault_path, notes))
    updated.append(_write_topics_index(vault_path, notes))
    updated.append(_write_entities_index(vault_path, notes))
    updated.append(_write_concepts_index(vault_path, notes))

    return updated


def _write_main_index(vault_path: Path, notes: list[VaultNote]) -> str:
    sources = [note for note in notes if note.note_type == "source"]
    raw_notes = [note for note in notes if note.note_type == "raw"]
    topics = [note for note in notes if note.note_type == "topic"]
    entities = [note for note in notes if note.note_type == "entity"]
    concepts = [note for note in notes if note.note_type == "concept"]
    synthesis = [note for note in notes if note.note_type == "synthesis"]

    source_type_counts = Counter(note.meta.get("source_type", "unknown") for note in sources)
    topic_counts = _reference_counts(sources, "topics")

    lines = [
        "# Knowledge Vault Index",
        "",
        f"> Last rebuilt: {friendly_date()}",
        "",
        "## Stats",
        "",
        "| Type | Count |",
        "|------|-------|",
        f"| Source notes | {len(sources)} |",
        f"| Raw captures | {len(raw_notes)} |",
        f"| Topics | {len(topics)} |",
        f"| Entities | {len(entities)} |",
        f"| Concepts | {len(concepts)} |",
        f"| Synthesis | {len(synthesis)} |",
        "",
        "## Navigation",
        "",
        f"- {wikilink('TOPICS')}",
        f"- {wikilink('ENTITIES')}",
        f"- {wikilink('CONCEPTS')}",
        f"- {path_wikilink('wiki/logs/ingest-log.md', 'Ingest Log')}",
        f"- {path_wikilink('wiki/logs/lint-log.md', 'Lint Log')}",
        "",
        "## Source Breakdown",
        "",
    ]

    if source_type_counts:
        for source_type, count in sorted(source_type_counts.items()):
            lines.append(f"- `{source_type}`: {count}")
    else:
        lines.append("- _No source notes yet_")

    lines.extend(["", "## Strongest Topic Areas", ""])
    if topic_counts:
        for topic, count in topic_counts.most_common(10):
            lines.append(f"- {wikilink(topic)} ({count} source note{'s' if count != 1 else ''})")
    else:
        lines.append("- _No topic references yet_")

    lines.extend(["", "## Recent Sources", ""])
    recent_sources = sorted(
        sources,
        key=lambda note: note.meta.get("ingested_at", ""),
        reverse=True,
    )[:20]
    if recent_sources:
        for note in recent_sources:
            source_type = note.meta.get("source_type", "unknown")
            quality = note.meta.get("extraction_quality", "unknown")
            lines.append(f"- {wikilink(note.title)} — `{source_type}` / `{quality}`")
    else:
        lines.append("- _No recent sources yet_")

    content = "\n".join(lines) + "\n"
    path = paths.index_path(vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path.relative_to(vault_path))


def _write_topics_index(vault_path: Path, notes: list[VaultNote]) -> str:
    topics = sorted(
        [note for note in notes if note.note_type == "topic"],
        key=lambda note: note.title.lower(),
    )
    topic_counts = _reference_counts(
        [note for note in notes if note.note_type == "source"],
        "topics",
    )
    lines = [f"# Topics Index\n\n> Last rebuilt: {friendly_date()}\n"]
    if topics:
        for note in topics:
            count = topic_counts.get(note.title, 0)
            suffix = "s" if count != 1 else ""
            lines.append(f"- {wikilink(note.title)} ({count} source note{suffix})")
    else:
        lines.append("- _No topic pages yet_")
    path = paths.topics_index_path(vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path.relative_to(vault_path))


def _write_entities_index(vault_path: Path, notes: list[VaultNote]) -> str:
    entities = sorted(
        [note for note in notes if note.note_type == "entity"],
        key=lambda note: note.title.lower(),
    )
    entity_counts = _reference_counts(
        [note for note in notes if note.note_type == "source"],
        "entities",
    )
    lines = [f"# Entities Index\n\n> Last rebuilt: {friendly_date()}\n"]
    if entities:
        for note in entities:
            entity_type = note.meta.get("entity_type", "")
            label = f" ({entity_type})" if entity_type else ""
            count = entity_counts.get(note.title, 0)
            lines.append(
                f"- {wikilink(note.title)}{label} ({count} source note{'s' if count != 1 else ''})"
            )
    else:
        lines.append("- _No entity pages yet_")
    path = paths.entities_index_path(vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path.relative_to(vault_path))


def _write_concepts_index(vault_path: Path, notes: list[VaultNote]) -> str:
    concepts = sorted(
        [note for note in notes if note.note_type == "concept"],
        key=lambda note: note.title.lower(),
    )
    concept_counts = _reference_counts(
        [note for note in notes if note.note_type == "source"],
        "concepts",
    )
    lines = [f"# Concepts Index\n\n> Last rebuilt: {friendly_date()}\n"]
    if concepts:
        for note in concepts:
            count = concept_counts.get(note.title, 0)
            suffix = "s" if count != 1 else ""
            lines.append(f"- {wikilink(note.title)} ({count} source note{suffix})")
    else:
        lines.append("- _No concept pages yet_")
    path = paths.concepts_index_path(vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path.relative_to(vault_path))


def _reference_counts(source_notes: list[VaultNote], field: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for note in source_notes:
        for value in note.meta.get(field, []) or []:
            if value:
                counts[value] += 1
    return counts
