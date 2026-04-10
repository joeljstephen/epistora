"""Read-model-native retrieval orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.read_model import (
    RELATION_BACKLINK,
    RELATION_CONCEPT_RELATIONSHIP,
    RELATION_DERIVED_FROM,
    RELATION_ENTITY_MENTION,
    RELATION_SOURCE_SUPPORT,
    RELATION_TOPIC_MEMBERSHIP,
    ReadModelNote,
    ReadModelStore,
)

SEARCHABLE_NOTE_TYPES = {"source", "topic", "entity", "concept", "synthesis"}
_RELATION_WEIGHTS = {
    RELATION_SOURCE_SUPPORT: 3.0,
    RELATION_DERIVED_FROM: 2.8,
    RELATION_TOPIC_MEMBERSHIP: 2.2,
    RELATION_ENTITY_MENTION: 2.0,
    RELATION_CONCEPT_RELATIONSHIP: 1.8,
    RELATION_BACKLINK: 1.1,
}


@dataclass(slots=True)
class RetrievedArtifact:
    note: ReadModelNote
    score: float
    reasons: list[str] = field(default_factory=list)
    snippet: str = ""


@dataclass(slots=True)
class RetrievalContext:
    question: str
    artifacts: list[RetrievedArtifact]
    source_references: list[str]
    topics_consulted: list[str]
    text_context: str


def build_retrieval_context(vault_path: Path, question: str, *, limit: int = 8) -> RetrievalContext:
    store = ReadModelStore(vault_path)
    store.ensure_populated()

    merged: dict[str, dict[str, object]] = {}
    for hit in store.search_structured(
        question,
        limit=max(limit, 8),
        note_types=SEARCHABLE_NOTE_TYPES,
    ):
        merged[str(hit["note_path"])] = {
            **hit,
            "score": float(hit["score"]),
            "reasons": list(hit.get("reasons", [])),
        }

    for rank, hit in enumerate(
        store.search_lexical(question, limit=max(limit, 10), note_types=SEARCHABLE_NOTE_TYPES),
        start=1,
    ):
        note_path = str(hit["note_path"])
        lexical_bonus = max(1.0, 4.0 - ((rank - 1) * 0.4))
        existing = merged.setdefault(
            note_path,
            {
                **hit,
                "score": 0.0,
                "reasons": [],
            },
        )
        existing["score"] = float(existing["score"]) + lexical_bonus
        reasons = list(existing.get("reasons", []))
        reasons.append("lexical support")
        existing["reasons"] = list(dict.fromkeys(reasons))
        if not existing.get("snippet") and hit.get("snippet"):
            existing["snippet"] = hit["snippet"]

    primary_paths = [
        path
        for path, _ in sorted(
            merged.items(),
            key=lambda item: (-float(item[1]["score"]), str(item[1].get("title", ""))),
        )[: max(4, min(limit, 6))]
    ]

    for note_path in primary_paths:
        _expand_neighbors(store, note_path, merged)

    ordered_paths = [
        path
        for path, _ in sorted(
            merged.items(),
            key=lambda item: (-float(item[1]["score"]), str(item[1].get("title", ""))),
        )[:limit]
    ]

    artifacts: list[RetrievedArtifact] = []
    source_references: list[str] = []
    topics_consulted: list[str] = []
    context_parts: list[str] = _index_previews(vault_path)

    for note_path in ordered_paths:
        note = store.get_note(note_path)
        if note is None:
            continue
        reasons = list(
            dict.fromkeys(str(reason) for reason in merged[note_path].get("reasons", []))
        )
        snippet = str(merged[note_path].get("snippet") or store.make_snippet(note, question))
        relation_summary = _relation_summary(store, note)
        artifacts.append(
            RetrievedArtifact(
                note=note,
                score=float(merged[note_path]["score"]),
                reasons=reasons,
                snippet=snippet,
            )
        )
        source_references.append(note.note_path)
        if note.note_type == "topic":
            topics_consulted.append(note.title)
        context_parts.append(
            "\n".join(
                [
                    f"### {note.note_type}: {note.title}",
                    f"Path: {note.note_path}",
                    f"Why retrieved: {', '.join(reasons) if reasons else 'read-model candidate'}",
                    relation_summary,
                    snippet or "No excerpt available.",
                ]
            ).strip()
        )

    if not artifacts:
        context_parts.append("No relevant notes found in the read model.")

    return RetrievalContext(
        question=question,
        artifacts=artifacts,
        source_references=list(dict.fromkeys(source_references)),
        topics_consulted=list(dict.fromkeys(topics_consulted)),
        text_context="\n\n".join(part for part in context_parts if part),
    )


def _expand_neighbors(
    store: ReadModelStore,
    note_path: str,
    merged: dict[str, dict[str, object]],
) -> None:
    base = merged.get(note_path)
    if base is None:
        return

    for edge in store.get_edges(from_note_path=note_path):
        neighbor_path = edge.to_note_path
        if not neighbor_path or edge.relation_type not in _RELATION_WEIGHTS:
            continue
        _merge_neighbor(
            store,
            merged,
            neighbor_path,
            bonus=_RELATION_WEIGHTS[edge.relation_type],
            reason=f"{edge.relation_type} expansion",
        )

    for edge in store.get_edges(to_note_path=note_path):
        neighbor_path = edge.from_note_path
        if not neighbor_path or edge.relation_type not in _RELATION_WEIGHTS:
            continue
        _merge_neighbor(
            store,
            merged,
            neighbor_path,
            bonus=max(0.8, _RELATION_WEIGHTS[edge.relation_type] - 0.4),
            reason=f"incoming {edge.relation_type}",
        )


def _merge_neighbor(
    store: ReadModelStore,
    merged: dict[str, dict[str, object]],
    note_path: str,
    *,
    bonus: float,
    reason: str,
) -> None:
    note = store.get_note(note_path)
    if note is None or note.note_type not in SEARCHABLE_NOTE_TYPES:
        return
    existing = merged.setdefault(
        note_path,
        {
            "note_path": note.note_path,
            "title": note.title,
            "note_type": note.note_type,
            "score": 0.0,
            "reasons": [],
            "snippet": store.make_snippet(note, note.title),
        },
    )
    existing["score"] = float(existing["score"]) + bonus
    reasons = list(existing.get("reasons", []))
    reasons.append(reason)
    existing["reasons"] = list(dict.fromkeys(reasons))


def _relation_summary(store: ReadModelStore, note: ReadModelNote) -> str:
    lines: list[str] = []

    supporting = [
        edge.target_title
        for edge in store.get_edges(
            from_note_path=note.note_path,
            relation_type=RELATION_SOURCE_SUPPORT,
        )
    ]
    if supporting:
        lines.append(f"Supporting sources: {', '.join(supporting[:4])}")

    derived_from = [
        edge.target_title
        for edge in store.get_edges(
            from_note_path=note.note_path,
            relation_type=RELATION_DERIVED_FROM,
        )
    ]
    if derived_from:
        lines.append(f"Derived from: {', '.join(derived_from[:4])}")

    memberships = []
    for relation_type in (
        RELATION_TOPIC_MEMBERSHIP,
        RELATION_ENTITY_MENTION,
        RELATION_CONCEPT_RELATIONSHIP,
    ):
        memberships.extend(
            edge.target_title
            for edge in store.get_edges(from_note_path=note.note_path, relation_type=relation_type)
            if edge.target_title
        )
    if memberships:
        lines.append(f"Linked concepts/entities/topics: {', '.join(memberships[:5])}")

    backlinks = store.get_backlinks(note.note_path)
    if backlinks:
        lines.append(f"Backlinks: {len(backlinks)}")

    return "Relationships: " + ("; ".join(lines) if lines else "None recorded")


def _index_previews(vault_path: Path) -> list[str]:
    index_dir = vault_path / "wiki" / "indexes"
    if not index_dir.exists():
        return []
    previews: list[str] = []
    for index_file in sorted(index_dir.glob("*.md")):
        preview = index_file.read_text(encoding="utf-8")[:1200].strip()
        if preview:
            previews.append(f"### index: {index_file.stem}\n{preview}")
    return previews[:3]
