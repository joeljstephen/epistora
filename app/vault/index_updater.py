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
    updated.append(_write_start_here(vault_path, notes))
    updated.append(_write_query_protocol(vault_path, notes))

    return updated


def _write_main_index(vault_path: Path, notes: list[VaultNote]) -> str:
    sources = [note for note in notes if note.note_type == "source"]
    raw_notes = [note for note in notes if note.note_type == "raw"]
    topics = [note for note in notes if note.note_type == "topic"]
    entities = [note for note in notes if note.note_type == "entity"]
    concepts = [note for note in notes if note.note_type == "concept"]
    synthesis = [note for note in notes if note.note_type == "synthesis"]

    source_type_counts = Counter(note.meta.get("source_type", "unknown") for note in sources)
    raw_kind_counts = Counter(
        (note.meta.get("raw_capture_kind") or "untyped_raw_capture") for note in raw_notes
    )
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
        "## Layer Responsibilities",
        "",
        "- `inbox/raw/` stores immutable evidence captures.",
        "- `wiki/` stores compiled notes, maintained pages, indexes, and logs.",
        "- `outputs/` stores temporary or user-requested artifacts until promoted.",
        "",
        "## Source Breakdown",
        "",
    ]

    if source_type_counts:
        for source_type, count in sorted(source_type_counts.items()):
            lines.append(f"- `{source_type}`: {count}")
    else:
        lines.append("- _No source notes yet_")

    lines.extend(["", "## Raw Evidence Breakdown", ""])
    if raw_kind_counts:
        for raw_kind, count in sorted(raw_kind_counts.items()):
            lines.append(f"- `{raw_kind}`: {count}")
    else:
        lines.append("- _No raw captures yet_")

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
            raw_kind = note.meta.get("raw_capture_kind") or "untyped_raw_capture"
            lines.append(
                f"- {wikilink(note.title)} — `{source_type}` / `{quality}` / raw `{raw_kind}`"
            )
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


def _write_start_here(vault_path: Path, notes: list[VaultNote]) -> str:
    sources = [n for n in notes if n.note_type == "source"]
    topics = [n for n in notes if n.note_type == "topic"]
    entities = [n for n in notes if n.note_type == "entity"]
    concepts = [n for n in notes if n.note_type == "concept"]
    synthesis = [n for n in notes if n.note_type == "synthesis"]
    raw_notes = [n for n in notes if n.note_type == "raw"]

    strong_topics = _reference_counts(sources, "topics").most_common(5)
    strong_entities = _reference_counts(sources, "entities").most_common(5)

    lines = [
        "# Start Here — Vault Orientation",
        "",
        f"> Last rebuilt: {friendly_date()}",
        "",
        "This file is the entry point for agents and humans navigating this vault.",
        "Read this first, then use the indexes and hub pages to find what you need.",
        "",
        "## Vault Layers",
        "",
        "| Layer | Location | Purpose | Trust Level |",
        "|-------|----------|---------|-------------|",
        "| Evidence | `inbox/raw/` | Immutable source captures | Escalation only |",
        "| Knowledge | `wiki/` | Compiled, maintained notes | Primary |",
        "| Scratch | `outputs/` | Temporary or user-requested artifacts | Unverified |",
        "",
        "## Current Vault Stats",
        "",
        f"- **{len(sources)}** source notes",
        f"- **{len(raw_notes)}** raw captures",
        f"- **{len(topics)}** topic pages",
        f"- **{len(entities)}** entity pages",
        f"- **{len(concepts)}** concept pages",
        f"- **{len(synthesis)}** synthesis notes",
        "",
        "## How to Route Your Question",
        "",
        "| Question Type | Start At | Then Read |",
        "|---------------|----------|-----------|",
        "| Topic overview | TOPICS.md | Topic page → source notes |",
        "| Specific claim | INDEX.md | Source notes w/ keywords |",
        "| Entity profile | ENTITIES.md | Entity page → source list |",
        "| Concept def | CONCEPTS.md | Concept page → examples |",
        "| Comparison | Both pages | Source notes for each side |",
        "| Gap analysis | All indexes | Note what is thin |",
        "| Learning path | Topic page | Suggested reading section |",
        "",
        "## Strongest Topic Areas",
        "",
    ]

    if strong_topics:
        for topic_name, count in strong_topics:
            lines.append(f"- {wikilink(topic_name)} ({count} sources)")
    else:
        lines.append("- _No topic references yet — ingest sources to build the vault_")

    lines.extend(["", "## Most-Referenced Entities", ""])

    if strong_entities:
        for entity_name, count in strong_entities:
            lines.append(f"- {wikilink(entity_name)} ({count} sources)")
    else:
        lines.append("- _No entity references yet_")

    lines.extend(
        [
            "",
            "## Navigation Files",
            "",
            f"- {wikilink('AGENTS')} — Full operating manual and conventions",
            f"- {wikilink('QUERY_PROTOCOL')} — Step-by-step query procedure",
            f"- {wikilink('INDEX')} — Complete vault index with stats",
            f"- {wikilink('TOPICS')} — All topic pages",
            f"- {wikilink('ENTITIES')} — All entity pages",
            f"- {wikilink('CONCEPTS')} — All concept pages",
            f"- {path_wikilink('wiki/logs/ingest-log.md', 'Ingest Log')}",
            "  — What was ingested and when",
            "",
            "## Quick Rules",
            "",
            "- Read source notes (`wiki/sources/`) first for grounded evidence",
            "- Use topic/entity/concept pages as routing hubs",
            "- Only read raw captures (`inbox/raw/`) when evidence quality "
            "is weak or exact text matters",
            "- Ignore `.system/` — it is internal state, not knowledge",
            "- Structure answers with: Direct Findings, "
            "Cross-Source Synthesis, Gaps, Relevant Notes",
            "",
        ]
    )

    content = "\n".join(lines)
    path = paths.start_here_path(vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path.relative_to(vault_path))


def _write_query_protocol(vault_path: Path, notes: list[VaultNote]) -> str:
    lines = [
        "# Query Protocol — Standard Agent Procedure",
        "",
        f"> Last rebuilt: {friendly_date()}",
        "",
        "This file defines the standard procedure for answering knowledge questions",
        "from this vault. Follow these steps in order.",
        "",
        "## Step 1: Orient",
        "",
        "Read these files first:",
        "",
        "1. `AGENTS.md` — vault conventions and operating manual",
        "2. `wiki/indexes/START_HERE.md` — vault orientation and routing",
        "3. `wiki/indexes/INDEX.md` — full vault overview",
        "",
        "## Step 2: Classify the Question",
        "",
        "Identify which type of question this is:",
        "",
        "- **Topic overview** — broad subject question → start at TOPICS.md",
        "- **Comparison** — how X and Y relate → find both topic/entity pages",
        "- **Evidence lookup** — specific claim → search source notes directly",
        "- **Gap analysis** — what is missing → scan all indexes for thin areas",
        "- **Entity profile** — person/company/tool → start at ENTITIES.md",
        "- **Learning path** — what to read next → topic page → suggested reading",
        "",
        "## Step 3: Find Candidate Notes",
        "",
        "Use the index files to identify relevant notes:",
        "",
        "1. Read `wiki/indexes/TOPICS.md` for topic matches",
        "2. Read `wiki/indexes/ENTITIES.md` for entity matches",
        "3. Read `wiki/indexes/CONCEPTS.md` for concept matches",
        "4. Read `wiki/indexes/INDEX.md` for recent sources that may be relevant",
        "",
        "## Step 4: Read Frontmatter Before Body",
        "",
        "For each candidate note, read only the YAML frontmatter first. Check:",
        "",
        "- `type` — is this the right note type?",
        "- `topics`, `entities`, `concepts` — does it match the question?",
        "- `extraction_quality` — how reliable is the evidence?",
        "- `source_url` — is this the right source?",
        "- `raw_capture_path` — where is the underlying evidence?",
        "",
        "Only read the full body for notes that pass this filter.",
        "",
        "## Step 5: Read Hub Pages",
        "",
        "Read relevant topic, entity, or concept pages. These pages serve as hubs:",
        "",
        "- They accumulate knowledge across multiple sources",
        "- They contain `[[wikilinks]]` to related source notes",
        "- They surface recurring patterns and contradictions",
        "",
        "## Step 6: Read Source Notes",
        "",
        "Source notes are the primary evidence. For each relevant source note:",
        "",
        "1. Check `Coverage & Limits` section for extraction quality",
        "2. Read `Key Ideas` and `Detailed Outline` for quick orientation",
        "3. Read `5-Minute Read` or `Detailed Reading Note` for depth",
        "4. Check `Open Questions` for unresolved issues",
        "5. Follow `[[wikilinks]]` in `Related Notes` for more context",
        "",
        "## Step 7: Escalate to Raw Captures (Only If Needed)",
        "",
        "Read raw captures ONLY when:",
        "",
        "- The source note has `extraction_quality` of `partial`, `metadata_only`, or `failed`",
        "- You need exact wording or exact evidence",
        "- The compiled note seems too compressed or missing details",
        "- You want to verify a specific claim against the original text",
        "",
        "Do NOT read raw captures by default. They are large and mostly redundant",
        "with the compiled source notes.",
        "",
        "## Step 8: Check Synthesis Notes",
        "",
        "If `wiki/synthesis/` contains relevant notes, read them. These represent",
        "prior cross-source work. Check their `Source Basis` section for grounding.",
        "",
        "## Step 9: Structure Your Answer",
        "",
        "Use this standard structure for all knowledge answers:",
        "",
        "```",
        "## Direct Findings",
        "- Grounded claims with explicit source references",
        "",
        "## Cross-Source Synthesis",
        "- Patterns, agreements, or tensions across sources",
        "",
        "## Gaps / Open Questions",
        "- What the vault does not cover or where evidence is weak",
        "",
        "## Relevant Notes to Read Next",
        "- Note paths or [[wikilinks]] for follow-up",
        "```",
        "",
        "## Answer Rules",
        "",
        "1. Ground every claim in a specific source note or raw capture",
        "2. Surface contradictions — do not smooth them away",
        "3. Note uncertainty when evidence quality is weak",
        "4. Do not invent evidence — state what is missing",
        "5. Reference notes by path or wikilink",
        "6. Distinguish direct findings from synthesis or inference",
        "",
        "## Evidence Trust Order",
        "",
        "1. Compiled source notes (`wiki/sources/`) — primary evidence",
        "2. Synthesis notes (`wiki/synthesis/`) — prior cross-source work",
        "3. Hub pages (`wiki/topics/`, `wiki/entities/`, `wiki/concepts/`) — routing + patterns",
        "4. Raw captures (`inbox/raw/`) — escalation evidence only",
        "",
        "## What Not To Do",
        "",
        "- Do not read `.system/` for knowledge answers",
        "- Do not treat `outputs/` as canonical wiki pages",
        "- Do not edit raw captures",
        "- Do not make claims unsupported by the vault evidence",
        "- Do not pad answers with generic filler when evidence is thin",
        "",
    ]

    content = "\n".join(lines)
    path = paths.query_protocol_path(vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path.relative_to(vault_path))
