"""Derived SQLite read model built from vault files."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.read_model.models import ReadModelEdge, ReadModelNote
from app.vault.parser import VaultNote, scan_vault

logger = logging.getLogger(__name__)

READ_MODEL_SCHEMA_VERSION = "2"
SEARCHABLE_NOTE_TYPES = {"source", "topic", "entity", "concept", "synthesis"}

READ_MODEL_SCHEMA = """
CREATE TABLE IF NOT EXISTS read_model_notes (
    note_path TEXT PRIMARY KEY,
    note_type TEXT NOT NULL,
    title TEXT NOT NULL,
    source_url TEXT DEFAULT '',
    source_type TEXT DEFAULT '',
    extraction_quality TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    topics TEXT DEFAULT '[]',
    entities TEXT DEFAULT '[]',
    concepts TEXT DEFAULT '[]',
    outgoing_links TEXT DEFAULT '[]',
    body TEXT DEFAULT '',
    file_mtime_ns INTEGER DEFAULT 0,
    indexed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS read_model_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_note_path TEXT NOT NULL,
    to_note_path TEXT DEFAULT '',
    relation_type TEXT NOT NULL,
    target_title TEXT DEFAULT '',
    metadata TEXT DEFAULT '{}',
    indexed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS read_model_state (
    key TEXT PRIMARY KEY,
    value TEXT DEFAULT ''
);

CREATE VIRTUAL TABLE IF NOT EXISTS read_model_fts USING fts5(
    note_path UNINDEXED,
    title,
    body,
    note_type UNINDEXED,
    topics,
    entities,
    concepts,
    tags,
    tokenize='porter unicode61'
);

CREATE INDEX IF NOT EXISTS idx_read_model_notes_type
    ON read_model_notes(note_type);
CREATE INDEX IF NOT EXISTS idx_read_model_notes_title
    ON read_model_notes(title);
CREATE INDEX IF NOT EXISTS idx_read_model_edges_from
    ON read_model_edges(from_note_path);
CREATE INDEX IF NOT EXISTS idx_read_model_edges_to
    ON read_model_edges(to_note_path);
CREATE INDEX IF NOT EXISTS idx_read_model_edges_relation
    ON read_model_edges(relation_type);
"""

RELATION_TOPIC_MEMBERSHIP = "topic_membership"
RELATION_ENTITY_MENTION = "entity_mention"
RELATION_CONCEPT_RELATIONSHIP = "concept_relationship"
RELATION_BACKLINK = "backlink"
RELATION_SOURCE_SUPPORT = "source_support"
RELATION_DERIVED_FROM = "derived_from"

# Backward-compatible aliases for older internal imports.
RELATION_WIKILINK = RELATION_BACKLINK
RELATION_SOURCE_TOPIC = RELATION_TOPIC_MEMBERSHIP
RELATION_SOURCE_ENTITY = RELATION_ENTITY_MENTION
RELATION_SOURCE_CONCEPT = RELATION_CONCEPT_RELATIONSHIP

_STRUCTURED_TERM_RE = re.compile(r"[a-z0-9]+")
_HUB_NOTE_TYPES = {"topic", "entity", "concept", "synthesis"}
_RELATION_WEIGHTS = {
    RELATION_SOURCE_SUPPORT: 3.0,
    RELATION_DERIVED_FROM: 3.0,
    RELATION_TOPIC_MEMBERSHIP: 2.2,
    RELATION_ENTITY_MENTION: 2.0,
    RELATION_CONCEPT_RELATIONSHIP: 1.9,
    RELATION_BACKLINK: 1.2,
}


class ReadModelStore:
    """Maintain a rebuildable read model derived from markdown vault files."""

    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        self.db_path = vault_path / ".system" / "state" / "read_model.db"

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        migrated = self._migrate_schema(conn)
        conn.executescript(READ_MODEL_SCHEMA)
        self._retire_legacy_search_state()
        if migrated:
            conn.commit()
        return conn

    def rebuild(self) -> dict[str, int]:
        """Full rebuild from vault files."""
        conn = self._connect()
        try:
            conn.execute("DELETE FROM read_model_edges")
            conn.execute("DELETE FROM read_model_notes")
            conn.execute("DELETE FROM read_model_fts")

            notes = [self._note_record(note) for note in scan_vault(self.vault_path)]
            self._upsert_notes(conn, notes)
            title_map = self._title_map(conn)

            edge_count = 0
            for note in scan_vault(self.vault_path):
                edges = self._edge_records(note, title_map)
                self._insert_edges(conn, edges)
                edge_count += len(edges)

            self._set_state(conn, "last_full_rebuild_at", _utcnow().isoformat())
            self._set_state(conn, "last_refresh_mode", "full")
            conn.commit()
            return {"notes": len(notes), "edges": edge_count}
        finally:
            conn.close()

    def refresh_paths(self, rel_paths: list[str]) -> dict[str, int | str]:
        """Incrementally refresh changed note paths when possible."""
        normalized = sorted({path for path in rel_paths if path.endswith(".md")})
        if not normalized:
            return {"mode": "noop", "notes": 0, "edges": 0}

        conn = self._connect()
        try:
            existing_titles = self._existing_titles(conn, normalized)
            parsed_notes: dict[str, VaultNote] = {}
            missing_paths: set[str] = set()

            for rel_path in normalized:
                abs_path = self.vault_path / rel_path
                visible_markdown = (
                    ".system" not in abs_path.parts and not abs_path.name.startswith(".")
                )
                if abs_path.exists() and visible_markdown:
                    parsed_notes[rel_path] = VaultNote(abs_path, self.vault_path)
                else:
                    missing_paths.add(rel_path)

            if self._title_changed(existing_titles, parsed_notes):
                logger.info(
                    "Read model incremental refresh fell back to full rebuild due to title change"
                )
                rebuilt = self.rebuild()
                return {"mode": "full_rebuild", **rebuilt}

            for rel_path in normalized:
                conn.execute("DELETE FROM read_model_edges WHERE from_note_path = ?", (rel_path,))
                conn.execute("DELETE FROM read_model_fts WHERE note_path = ?", (rel_path,))
                if rel_path in missing_paths:
                    conn.execute("DELETE FROM read_model_notes WHERE note_path = ?", (rel_path,))
                    conn.execute("DELETE FROM read_model_edges WHERE to_note_path = ?", (rel_path,))

            note_records = [self._note_record(note) for note in parsed_notes.values()]
            self._upsert_notes(conn, note_records)

            title_map = self._title_map(conn)
            edge_count = 0
            for note in parsed_notes.values():
                edges = self._edge_records(note, title_map)
                self._insert_edges(conn, edges)
                edge_count += len(edges)

            self._set_state(conn, "last_incremental_refresh_at", _utcnow().isoformat())
            self._set_state(conn, "last_refresh_mode", "incremental")
            conn.commit()
            return {"mode": "incremental", "notes": len(note_records), "edges": edge_count}
        finally:
            conn.close()

    def ensure_populated(self) -> None:
        conn = self._connect()
        try:
            note_count = conn.execute("SELECT COUNT(*) AS count FROM read_model_notes").fetchone()
            if note_count and int(note_count["count"]) > 0:
                return
        finally:
            conn.close()
        self.rebuild()

    def list_notes(self, *, note_type: str | None = None, limit: int = 100) -> list[ReadModelNote]:
        conn = self._connect()
        try:
            if note_type:
                rows = conn.execute(
                    """
                    SELECT * FROM read_model_notes
                    WHERE note_type = ?
                    ORDER BY title
                    LIMIT ?
                    """,
                    (note_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM read_model_notes ORDER BY note_type, title LIMIT ?",
                    (limit,),
                ).fetchall()
            return [self._row_to_note(row) for row in rows]
        finally:
            conn.close()

    def get_note(self, note_path: str) -> ReadModelNote | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM read_model_notes WHERE note_path = ?",
                (note_path,),
            ).fetchone()
            return self._row_to_note(row) if row else None
        finally:
            conn.close()

    def get_edges(
        self,
        *,
        from_note_path: str | None = None,
        to_note_path: str | None = None,
        relation_type: str | None = None,
    ) -> list[ReadModelEdge]:
        conn = self._connect()
        try:
            clauses: list[str] = []
            params: list[str] = []
            if from_note_path:
                clauses.append("from_note_path = ?")
                params.append(from_note_path)
            if to_note_path:
                clauses.append("to_note_path = ?")
                params.append(to_note_path)
            if relation_type:
                clauses.append("relation_type = ?")
                params.append(relation_type)

            query = "SELECT * FROM read_model_edges"
            if clauses:
                query += " WHERE " + " AND ".join(clauses)
            query += " ORDER BY from_note_path, relation_type, target_title"
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_edge(row) for row in rows]
        finally:
            conn.close()

    def get_backlinks(self, note_path: str) -> list[ReadModelEdge]:
        return self.get_edges(to_note_path=note_path, relation_type=RELATION_BACKLINK)

    def get_related_for_source(self, note_path: str) -> list[ReadModelEdge]:
        return self.get_edges(from_note_path=note_path)

    def get_state(self, key: str) -> str | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT value FROM read_model_state WHERE key = ?",
                (key,),
            ).fetchone()
            return str(row["value"]) if row else None
        finally:
            conn.close()

    def search_structured(
        self,
        query: str,
        *,
        limit: int = 15,
        note_types: set[str] | None = None,
    ) -> list[dict[str, object]]:
        self.ensure_populated()
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM read_model_notes ORDER BY note_type, title"
            ).fetchall()
        finally:
            conn.close()

        phrase = query.strip().lower()
        terms = _tokenize(query)
        if not terms:
            return []

        scored: list[tuple[float, dict[str, object]]] = []
        for row in rows:
            note = self._row_to_note(row)
            if note_types and note.note_type not in note_types:
                continue
            score, reasons = self._structured_score(note, phrase=phrase, terms=terms)
            if score <= 0:
                continue
            if note.note_type in _HUB_NOTE_TYPES:
                score += 0.5
                reasons.append("hub artifact")
            scored.append(
                (
                    score,
                    {
                        "note_path": note.note_path,
                        "title": note.title,
                        "note_type": note.note_type,
                        "snippet": self.make_snippet(note, query),
                        "score": score,
                        "reasons": list(dict.fromkeys(reasons)),
                    },
                )
            )

        scored.sort(key=lambda item: (-item[0], str(item[1]["title"])))
        return [item for _, item in scored[:limit]]

    def search_lexical(
        self,
        query: str,
        *,
        limit: int = 15,
        note_types: set[str] | None = None,
    ) -> list[dict[str, object]]:
        self.ensure_populated()
        terms = _tokenize(query)
        if not terms:
            return []

        conn = self._connect()
        try:
            if not self._fts_has_rows(conn):
                return []

            params: list[object] = [" OR ".join(terms)]
            type_clause = ""
            if note_types:
                placeholders = ",".join("?" for _ in note_types)
                type_clause = f" AND note_type IN ({placeholders})"
                params.extend(sorted(note_types))
            params.append(limit)

            rows = conn.execute(
                f"""
                SELECT note_path, title, note_type,
                       snippet(read_model_fts, 2, '', '', '...', 40) AS snippet,
                       bm25(read_model_fts) AS score
                FROM read_model_fts
                WHERE read_model_fts MATCH ?{type_clause}
                ORDER BY score
                LIMIT ?
                """,
                params,
            ).fetchall()
        except sqlite3.Error:
            logger.warning("Read-model lexical search failed", exc_info=True)
            return []
        finally:
            conn.close()

        return [
            {
                "note_path": str(row["note_path"]),
                "title": str(row["title"]),
                "note_type": str(row["note_type"]),
                "snippet": str(row["snippet"] or ""),
                "score": float(row["score"] or 0.0),
            }
            for row in rows
        ]

    def make_snippet(self, note: ReadModelNote, query: str, window: int = 240) -> str:
        body = note.body.strip()
        if not body:
            related = ", ".join(note.topics + note.entities + note.concepts)
            body = related or note.title
        body = re.sub(r"\s+", " ", body).strip()
        if not body:
            return ""

        body_lower = body.lower()
        best_pos = -1
        for term in _tokenize(query):
            pos = body_lower.find(term)
            if pos != -1:
                best_pos = pos
                break

        if best_pos == -1:
            return body[:window].strip()

        start = max(0, best_pos - window // 3)
        end = min(len(body), best_pos + window // 2)
        snippet = body[start:end].strip()
        if start > 0:
            snippet = "..." + snippet
        if end < len(body):
            snippet = snippet + "..."
        return snippet

    def search_stats(self) -> dict[str, int | bool]:
        self.ensure_populated()
        conn = self._connect()
        try:
            documents = conn.execute("SELECT COUNT(*) AS count FROM read_model_fts").fetchone()
        finally:
            conn.close()
        return {
            "documents": int(documents["count"]) if documents else 0,
            "legacy_search_db_retired": not (
                self.vault_path / ".system" / "state" / "search.db"
            ).exists(),
        }

    def _migrate_schema(self, conn: sqlite3.Connection) -> bool:
        conn.executescript(READ_MODEL_SCHEMA)
        current_version = self._state_value(conn, "schema_version")

        note_columns = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(read_model_notes)").fetchall()
        }
        requires_reset = current_version != READ_MODEL_SCHEMA_VERSION or "body" not in note_columns
        if not requires_reset:
            return False

        conn.execute("DROP TABLE IF EXISTS read_model_fts")
        conn.execute("DROP TABLE IF EXISTS read_model_edges")
        conn.execute("DROP TABLE IF EXISTS read_model_notes")
        conn.executescript(READ_MODEL_SCHEMA)
        self._set_state(conn, "schema_version", READ_MODEL_SCHEMA_VERSION)
        self._set_state(conn, "last_schema_migration_at", _utcnow().isoformat())
        return True

    def _retire_legacy_search_state(self) -> None:
        legacy_path = self.vault_path / ".system" / "state" / "search.db"
        if legacy_path.exists():
            legacy_path.unlink(missing_ok=True)

    def _upsert_notes(self, conn: sqlite3.Connection, notes: list[ReadModelNote]) -> None:
        for note in notes:
            conn.execute(
                """
                INSERT INTO read_model_notes
                (note_path, note_type, title, source_url, source_type, extraction_quality,
                 tags, topics, entities, concepts, outgoing_links, body, file_mtime_ns, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(note_path) DO UPDATE SET
                  note_type = excluded.note_type,
                  title = excluded.title,
                  source_url = excluded.source_url,
                  source_type = excluded.source_type,
                  extraction_quality = excluded.extraction_quality,
                  tags = excluded.tags,
                  topics = excluded.topics,
                  entities = excluded.entities,
                  concepts = excluded.concepts,
                  outgoing_links = excluded.outgoing_links,
                  body = excluded.body,
                  file_mtime_ns = excluded.file_mtime_ns,
                  indexed_at = excluded.indexed_at
                """,
                (
                    note.note_path,
                    note.note_type,
                    note.title,
                    note.source_url,
                    note.source_type,
                    note.extraction_quality,
                    json.dumps(note.tags),
                    json.dumps(note.topics),
                    json.dumps(note.entities),
                    json.dumps(note.concepts),
                    json.dumps(note.outgoing_links),
                    note.body,
                    note.file_mtime_ns,
                    note.indexed_at.isoformat(),
                ),
            )
            conn.execute("DELETE FROM read_model_fts WHERE note_path = ?", (note.note_path,))
            if note.note_type in SEARCHABLE_NOTE_TYPES:
                conn.execute(
                    """
                    INSERT INTO read_model_fts
                    (note_path, title, body, note_type, topics, entities, concepts, tags)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        note.note_path,
                        note.title,
                        note.body,
                        note.note_type,
                        " ".join(note.topics),
                        " ".join(note.entities),
                        " ".join(note.concepts),
                        " ".join(note.tags),
                    ),
                )

    def _insert_edges(self, conn: sqlite3.Connection, edges: list[ReadModelEdge]) -> None:
        for edge in edges:
            conn.execute(
                """
                INSERT INTO read_model_edges
                (from_note_path, to_note_path, relation_type, target_title, metadata, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    edge.from_note_path,
                    edge.to_note_path,
                    edge.relation_type,
                    edge.target_title,
                    json.dumps(edge.metadata),
                    edge.indexed_at.isoformat(),
                ),
            )

    def _title_map(self, conn: sqlite3.Connection) -> dict[str, str]:
        rows = conn.execute(
            "SELECT title, note_path FROM read_model_notes ORDER BY note_path"
        ).fetchall()
        return {str(row["title"]): str(row["note_path"]) for row in rows}

    def _existing_titles(self, conn: sqlite3.Connection, rel_paths: list[str]) -> dict[str, str]:
        if not rel_paths:
            return {}
        placeholders = ",".join("?" for _ in rel_paths)
        rows = conn.execute(
            f"SELECT note_path, title FROM read_model_notes WHERE note_path IN ({placeholders})",
            rel_paths,
        ).fetchall()
        return {str(row["note_path"]): str(row["title"]) for row in rows}

    def _title_changed(
        self,
        existing_titles: dict[str, str],
        parsed_notes: dict[str, VaultNote],
    ) -> bool:
        for rel_path, old_title in existing_titles.items():
            note = parsed_notes.get(rel_path)
            if note is None:
                continue
            if note.title != old_title:
                return True
        return False

    def _note_record(self, note: VaultNote) -> ReadModelNote:
        file_stat = note.path.stat()
        return ReadModelNote(
            note_path=note.rel_path,
            note_type=note.note_type,
            title=note.title,
            source_url=str(note.meta.get("source_url", "") or ""),
            source_type=str(note.meta.get("source_type", "") or ""),
            extraction_quality=str(note.meta.get("extraction_quality", "") or ""),
            tags=_normalize_list(note.meta.get("tags", [])),
            topics=_normalize_list(note.meta.get("topics", [])),
            entities=_normalize_list(note.meta.get("entities", [])),
            concepts=_normalize_list(note.meta.get("concepts", [])),
            outgoing_links=list(note.outgoing_links),
            body=_normalized_body(note.body),
            file_mtime_ns=file_stat.st_mtime_ns,
            indexed_at=_utcnow(),
        )

    def _edge_records(self, note: VaultNote, title_map: dict[str, str]) -> list[ReadModelEdge]:
        now = _utcnow()
        edges: list[ReadModelEdge] = []

        for link_title in note.outgoing_links:
            edges.append(
                ReadModelEdge(
                    from_note_path=note.rel_path,
                    to_note_path=title_map.get(link_title, ""),
                    relation_type=RELATION_BACKLINK,
                    target_title=link_title,
                    indexed_at=now,
                )
            )

        for topic in _normalize_list(note.meta.get("topics", [])):
            topic_path = title_map.get(topic, "")
            edges.append(
                ReadModelEdge(
                    from_note_path=note.rel_path,
                    to_note_path=topic_path,
                    relation_type=RELATION_TOPIC_MEMBERSHIP,
                    target_title=topic,
                    indexed_at=now,
                )
            )
            if note.note_type == "source" and topic_path:
                edges.append(
                    ReadModelEdge(
                        from_note_path=topic_path,
                        to_note_path=note.rel_path,
                        relation_type=RELATION_SOURCE_SUPPORT,
                        target_title=note.title,
                        metadata={"supported_note_type": "topic"},
                        indexed_at=now,
                    )
                )

        for entity in _normalize_list(note.meta.get("entities", [])):
            entity_path = title_map.get(entity, "")
            edges.append(
                ReadModelEdge(
                    from_note_path=note.rel_path,
                    to_note_path=entity_path,
                    relation_type=RELATION_ENTITY_MENTION,
                    target_title=entity,
                    indexed_at=now,
                )
            )
            if note.note_type == "source" and entity_path:
                edges.append(
                    ReadModelEdge(
                        from_note_path=entity_path,
                        to_note_path=note.rel_path,
                        relation_type=RELATION_SOURCE_SUPPORT,
                        target_title=note.title,
                        metadata={"supported_note_type": "entity"},
                        indexed_at=now,
                    )
                )

        for concept in _normalize_list(note.meta.get("concepts", [])):
            concept_path = title_map.get(concept, "")
            edges.append(
                ReadModelEdge(
                    from_note_path=note.rel_path,
                    to_note_path=concept_path,
                    relation_type=RELATION_CONCEPT_RELATIONSHIP,
                    target_title=concept,
                    indexed_at=now,
                )
            )
            if note.note_type == "source" and concept_path:
                edges.append(
                    ReadModelEdge(
                        from_note_path=concept_path,
                        to_note_path=note.rel_path,
                        relation_type=RELATION_SOURCE_SUPPORT,
                        target_title=note.title,
                        metadata={"supported_note_type": "concept"},
                        indexed_at=now,
                    )
                )

        if note.note_type == "synthesis":
            for source_title in _normalize_list(note.meta.get("source_basis", [])):
                source_path = title_map.get(source_title, "")
                edges.append(
                    ReadModelEdge(
                        from_note_path=note.rel_path,
                        to_note_path=source_path,
                        relation_type=RELATION_DERIVED_FROM,
                        target_title=source_title,
                        indexed_at=now,
                    )
                )
            candidate_topic = str(note.meta.get("candidate_topic", "") or "").strip()
            if candidate_topic:
                edges.append(
                    ReadModelEdge(
                        from_note_path=note.rel_path,
                        to_note_path=title_map.get(candidate_topic, ""),
                        relation_type=RELATION_TOPIC_MEMBERSHIP,
                        target_title=candidate_topic,
                        indexed_at=now,
                    )
                )

        return edges

    def _structured_score(
        self,
        note: ReadModelNote,
        *,
        phrase: str,
        terms: list[str],
    ) -> tuple[float, list[str]]:
        score = 0.0
        reasons: list[str] = []
        title_lower = note.title.lower()
        path_lower = note.note_path.lower()
        body_lower = note.body.lower()

        if phrase and phrase in title_lower:
            score += 10.0
            reasons.append("title phrase match")
        if phrase and phrase in path_lower:
            score += 4.0
            reasons.append("path phrase match")

        for term in terms:
            if term in title_lower:
                score += 3.5
                reasons.append("title token match")
            if any(term in item.lower() for item in note.topics):
                score += 4.0
                reasons.append("topic membership")
            if any(term in item.lower() for item in note.entities):
                score += 3.5
                reasons.append("entity mention")
            if any(term in item.lower() for item in note.concepts):
                score += 3.2
                reasons.append("concept relationship")
            if term in path_lower:
                score += 1.2
                reasons.append("path token match")
            if term in body_lower:
                score += 0.8
                reasons.append("body token match")

        return score, reasons

    def _fts_has_rows(self, conn: sqlite3.Connection) -> bool:
        row = conn.execute("SELECT COUNT(*) AS count FROM read_model_fts").fetchone()
        return bool(row and int(row["count"]) > 0)

    def _set_state(self, conn: sqlite3.Connection, key: str, value: str) -> None:
        conn.execute(
            """
            INSERT INTO read_model_state (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )

    def _state_value(self, conn: sqlite3.Connection, key: str) -> str | None:
        row = conn.execute(
            "SELECT value FROM read_model_state WHERE key = ?",
            (key,),
        ).fetchone()
        return str(row["value"]) if row else None

    @staticmethod
    def _row_to_note(row: sqlite3.Row) -> ReadModelNote:
        payload = dict(row)
        for field in ("tags", "topics", "entities", "concepts", "outgoing_links"):
            payload[field] = _parse_json_list(payload.get(field))
        payload["body"] = str(payload.get("body", "") or "")
        payload["indexed_at"] = _parse_datetime(payload.get("indexed_at"))
        return ReadModelNote(**payload)

    @staticmethod
    def _row_to_edge(row: sqlite3.Row) -> ReadModelEdge:
        payload = dict(row)
        payload["metadata"] = _parse_json_dict(payload.get("metadata"))
        payload["indexed_at"] = _parse_datetime(payload.get("indexed_at"))
        payload.pop("id", None)
        return ReadModelEdge(**payload)


def _normalize_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    return [str(value)]


def _normalized_body(body: str, *, max_chars: int = 12000) -> str:
    collapsed = re.sub(r"\s+", " ", body).strip()
    return collapsed[:max_chars].strip()


def _parse_json_list(value: object) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        decoded = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    if isinstance(decoded, list):
        return [str(item) for item in decoded]
    return []


def _parse_json_dict(value: object) -> dict[str, object]:
    if not value:
        return {}
    if isinstance(value, dict):
        return dict(value)
    try:
        decoded = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    if isinstance(decoded, dict):
        return decoded
    return {}


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return _utcnow()


def _tokenize(query: str) -> list[str]:
    return list(dict.fromkeys(_STRUCTURED_TERM_RE.findall(query.lower())))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
