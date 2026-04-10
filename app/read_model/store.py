"""Derived SQLite read model built from vault files."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.read_model.models import ReadModelEdge, ReadModelNote
from app.vault.parser import VaultNote, scan_vault

logger = logging.getLogger(__name__)

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

RELATION_WIKILINK = "wikilink"
RELATION_SOURCE_TOPIC = "source_topic"
RELATION_SOURCE_ENTITY = "source_entity"
RELATION_SOURCE_CONCEPT = "source_concept"


class ReadModelStore:
    """Maintain a rebuildable read model derived from markdown vault files."""

    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        self.db_path = vault_path / ".system" / "state" / "read_model.db"

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.executescript(READ_MODEL_SCHEMA)
        return conn

    def rebuild(self) -> dict[str, int]:
        """Full rebuild from vault files."""
        conn = self._connect()
        try:
            conn.execute("DELETE FROM read_model_edges")
            conn.execute("DELETE FROM read_model_notes")
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
        return self.get_edges(to_note_path=note_path)

    def get_related_for_source(self, note_path: str) -> list[ReadModelEdge]:
        return self.get_edges(
            from_note_path=note_path,
        )

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

    def _upsert_notes(self, conn: sqlite3.Connection, notes: list[ReadModelNote]) -> None:
        for note in notes:
            conn.execute(
                """
                INSERT INTO read_model_notes
                (note_path, note_type, title, source_url, source_type, extraction_quality,
                 tags, topics, entities, concepts, outgoing_links, file_mtime_ns, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    note.file_mtime_ns,
                    note.indexed_at.isoformat(),
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
                    relation_type=RELATION_WIKILINK,
                    target_title=link_title,
                    indexed_at=now,
                )
            )

        if note.note_type == "source":
            for topic in _normalize_list(note.meta.get("topics", [])):
                edges.append(
                    ReadModelEdge(
                        from_note_path=note.rel_path,
                        to_note_path=title_map.get(topic, ""),
                        relation_type=RELATION_SOURCE_TOPIC,
                        target_title=topic,
                        indexed_at=now,
                    )
                )
            for entity in _normalize_list(note.meta.get("entities", [])):
                edges.append(
                    ReadModelEdge(
                        from_note_path=note.rel_path,
                        to_note_path=title_map.get(entity, ""),
                        relation_type=RELATION_SOURCE_ENTITY,
                        target_title=entity,
                        indexed_at=now,
                    )
                )
            for concept in _normalize_list(note.meta.get("concepts", [])):
                edges.append(
                    ReadModelEdge(
                        from_note_path=note.rel_path,
                        to_note_path=title_map.get(concept, ""),
                        relation_type=RELATION_SOURCE_CONCEPT,
                        target_title=concept,
                        indexed_at=now,
                    )
                )

        return edges

    def _set_state(self, conn: sqlite3.Connection, key: str, value: str) -> None:
        conn.execute(
            """
            INSERT INTO read_model_state (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )

    @staticmethod
    def _row_to_note(row: sqlite3.Row) -> ReadModelNote:
        payload = dict(row)
        for field in ("tags", "topics", "entities", "concepts", "outgoing_links"):
            payload[field] = _parse_json_list(payload.get(field))
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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
