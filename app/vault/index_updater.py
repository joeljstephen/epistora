"""Rebuild and update vault index files."""

from __future__ import annotations

from pathlib import Path

from app.utils.dates import friendly_date
from app.utils.markdown import wikilink
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
    sources = [n for n in notes if n.note_type == "source"]
    topics = [n for n in notes if n.note_type == "topic"]
    entities = [n for n in notes if n.note_type == "entity"]
    concepts = [n for n in notes if n.note_type == "concept"]
    synthesis = [n for n in notes if n.note_type == "synthesis"]

    body = f"""# Knowledge Vault Index

> Last rebuilt: {friendly_date()}

## Stats

| Type | Count |
|------|-------|
| Sources | {len(sources)} |
| Topics | {len(topics)} |
| Entities | {len(entities)} |
| Concepts | {len(concepts)} |
| Synthesis | {len(synthesis)} |

## Quick Links

- {wikilink("TOPICS")}
- {wikilink("ENTITIES")}
- {wikilink("CONCEPTS")}

## Recent Sources

"""
    for n in sorted(sources, key=lambda x: x.meta.get("ingested_at", ""), reverse=True)[:20]:
        body += f"- {wikilink(n.title)}\n"

    p = paths.index_path(vault_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return str(p.relative_to(vault_path))


def _write_topics_index(vault_path: Path, notes: list[VaultNote]) -> str:
    topics = sorted(
        [n for n in notes if n.note_type == "topic"],
        key=lambda x: x.title.lower()
    )
    lines = [f"# Topics Index\n\n> Last rebuilt: {friendly_date()}\n"]
    for n in topics:
        lines.append(f"- {wikilink(n.title)}")
    p = paths.topics_index_path(vault_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(p.relative_to(vault_path))


def _write_entities_index(vault_path: Path, notes: list[VaultNote]) -> str:
    entities = sorted(
        [n for n in notes if n.note_type == "entity"],
        key=lambda x: x.title.lower()
    )
    lines = [f"# Entities Index\n\n> Last rebuilt: {friendly_date()}\n"]
    for n in entities:
        etype = n.meta.get("entity_type", "")
        label = f" ({etype})" if etype else ""
        lines.append(f"- {wikilink(n.title)}{label}")
    p = paths.entities_index_path(vault_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(p.relative_to(vault_path))


def _write_concepts_index(vault_path: Path, notes: list[VaultNote]) -> str:
    concepts = sorted(
        [n for n in notes if n.note_type == "concept"],
        key=lambda x: x.title.lower()
    )
    lines = [f"# Concepts Index\n\n> Last rebuilt: {friendly_date()}\n"]
    for n in concepts:
        lines.append(f"- {wikilink(n.title)}")
    p = paths.concepts_index_path(vault_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(p.relative_to(vault_path))
