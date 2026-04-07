"""LangGraph ingest workflow — turns a SourceItem into vault notes."""

from __future__ import annotations

import json
import logging
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.compiler.llm import get_llm
from app.compiler.prompts import SOURCE_ANALYSIS_PROMPT, SYSTEM_ROLE
from app.connectors.fetchers import fetch_content
from app.models.db import ProcessedSource, VaultNoteMapping
from app.models.knowledge import Concept, Entity, Topic
from app.models.results import IngestResult, VaultUpdate
from app.models.source import SourceContent, SourceItem
from app.storage.repositories import SourceRepository, VaultNoteRepository
from app.storage.sqlite import Database
from app.utils.hashing import url_hash as compute_url_hash
from app.utils.slugify import slugify
from app.vault.index_updater import rebuild_indexes
from app.vault.log_updater import append_ingest_log
from app.vault.writer import VaultWriter

logger = logging.getLogger(__name__)


class IngestState(TypedDict, total=False):
    item: SourceItem
    content: SourceContent
    slug: str
    analysis: dict[str, Any]
    topics: list[Topic]
    entities: list[Entity]
    concepts: list[Concept]
    vault_updates: list[VaultUpdate]
    result: IngestResult
    deduplicated: bool
    duplicate_of: ProcessedSource
    error: str


async def _fetch_content(state: IngestState) -> IngestState:
    item = state["item"]
    content = await fetch_content(item)
    slug = slugify(content.source.title or item.url)
    return {**state, "content": content, "slug": slug}


async def _check_dedup(state: IngestState) -> IngestState:
    from app.config import get_settings

    content: SourceContent = state["content"]
    settings = get_settings()
    db = Database(settings.db_path)
    db.connect()

    try:
        source_repo = SourceRepository(db)

        existing = source_repo.find_by_url_hash(
            content.url_hash or compute_url_hash(content.source.url)
        )
        if existing is None and content.content_hash:
            existing = source_repo.find_by_content_hash(content.content_hash)

        if existing and existing.status == "completed":
            result = IngestResult(
                source_url=content.source.url,
                source_type=existing.source_type or content.source.source_type.value,
                source_note_path=existing.source_note_path,
                raw_capture_path=existing.raw_capture_path,
                deduplicated=True,
            )
            return {**state, "deduplicated": True, "duplicate_of": existing, "result": result}

        return state
    finally:
        db.close()


async def _analyse_content(state: IngestState) -> IngestState:
    content: SourceContent = state["content"]
    text = content.cleaned_text or content.raw_text

    if not text or content.extraction_quality == "failed":
        return {
            **state,
            "analysis": {
                "summary": "Content could not be extracted from this source.",
                "key_takeaways": "- Extraction failed or returned empty content",
                "detailed_outline": "N/A",
                "important_claims": "- None extractable",
                "why_matters": "Source was saved but content could not be automatically processed.",
                "open_questions": "- Why did extraction fail? Manual review recommended.",
                "topics": [],
                "entities": [],
                "concepts": [],
            },
        }

    truncated = text[:12000]
    llm = get_llm()

    prompt = SOURCE_ANALYSIS_PROMPT.format(
        title=content.source.title,
        source_type=content.source.source_type.value,
        url=content.source.url,
        content=truncated,
    )

    try:
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
            analysis = raw
    except Exception as e:
        logger.warning("LLM analysis failed: %s", e)
        analysis = {
            "summary": f"Auto-analysis failed ({e}). Manual review needed.",
            "key_takeaways": "- LLM analysis unavailable",
            "detailed_outline": truncated[:2000],
            "important_claims": "- See raw content",
            "why_matters": "Source saved for manual review.",
            "open_questions": "- Full analysis pending",
            "topics": [],
            "entities": [],
            "concepts": [],
        }

    return {**state, "analysis": analysis}


async def _extract_knowledge(state: IngestState) -> IngestState:
    analysis = state["analysis"]
    slug = state["slug"]

    topics = []
    for t_name in analysis.get("topics", []):
        t_slug = slugify(t_name)
        topics.append(Topic(name=t_name, slug=t_slug, source_ids=[slug]))

    entities = []
    for e_data in analysis.get("entities", []):
        if isinstance(e_data, str):
            e_data = {"name": e_data, "type": "unknown", "description": ""}
        e_slug = slugify(e_data["name"])
        entities.append(
            Entity(
                name=e_data["name"],
                slug=e_slug,
                entity_type=e_data.get("type", "unknown"),
                description=e_data.get("description", ""),
                source_ids=[slug],
            )
        )

    concepts = []
    for c_data in analysis.get("concepts", []):
        if isinstance(c_data, str):
            c_data = {"name": c_data, "definition": ""}
        c_slug = slugify(c_data["name"])
        concepts.append(
            Concept(
                name=c_data["name"],
                slug=c_slug,
                definition=c_data.get("definition", ""),
                source_ids=[slug],
            )
        )

    return {**state, "topics": topics, "entities": entities, "concepts": concepts}


async def _write_vault(state: IngestState) -> IngestState:
    from pathlib import Path

    from app.config import get_settings

    settings = get_settings()
    vault_path = Path(settings.vault_path)
    writer = VaultWriter(vault_path)
    writer.ensure_structure()

    content: SourceContent = state["content"]
    slug = state["slug"]
    analysis = state["analysis"]
    topics: list[Topic] = state.get("topics", [])
    entities: list[Entity] = state.get("entities", [])
    concepts: list[Concept] = state.get("concepts", [])

    updates: list[VaultUpdate] = []

    raw_update = writer.write_raw_capture(content, slug)
    updates.append(raw_update)

    source_update = writer.write_source_note(
        content=content,
        slug=slug,
        summary=analysis.get("summary", ""),
        key_takeaways=analysis.get("key_takeaways", ""),
        detailed_outline=analysis.get("detailed_outline", ""),
        important_claims=analysis.get("important_claims", ""),
        why_matters=analysis.get("why_matters", ""),
        open_questions=analysis.get("open_questions", ""),
        topics=[t.name for t in topics],
        entities=[e.name for e in entities],
        concepts=[c.name for c in concepts],
    )
    updates.append(source_update)

    source_title = content.source.title

    for topic in topics:
        u = writer.write_topic(topic, [source_title])
        updates.append(u)

    for entity in entities:
        u = writer.write_entity(entity, [source_title])
        updates.append(u)

    for concept in concepts:
        u = writer.write_concept(concept, [source_title])
        updates.append(u)

    rebuild_indexes(vault_path)

    return {**state, "vault_updates": updates}


async def _persist_duplicate(state: IngestState) -> IngestState:
    from pathlib import Path

    from app.config import get_settings

    settings = get_settings()
    vault_path = Path(settings.vault_path)
    db = Database(settings.db_path)
    db.connect()

    try:
        content: SourceContent = state["content"]
        existing = state["duplicate_of"]
        result = state["result"]

        SourceRepository(db).upsert(
            ProcessedSource(
                url=content.source.url,
                url_hash=content.url_hash or compute_url_hash(content.source.url),
                content_hash=content.content_hash or existing.content_hash,
                source_type=existing.source_type or content.source.source_type.value,
                title=content.source.title or existing.title,
                source_note_path=existing.source_note_path,
                raw_capture_path=existing.raw_capture_path,
                raindrop_id=content.source.raindrop_id,
                status="completed",
            )
        )

        append_ingest_log(vault_path, result)
        return state
    finally:
        db.close()


async def _persist_state(state: IngestState) -> IngestState:
    from pathlib import Path

    from app.config import get_settings

    settings = get_settings()
    vault_path = Path(settings.vault_path)
    db = Database(settings.db_path)
    db.connect()

    content: SourceContent = state["content"]
    slug = state["slug"]
    updates: list[VaultUpdate] = state.get("vault_updates", [])
    topics: list[Topic] = state.get("topics", [])
    entities: list[Entity] = state.get("entities", [])
    concepts: list[Concept] = state.get("concepts", [])

    source_repo = SourceRepository(db)
    note_repo = VaultNoteRepository(db)

    source_note_path = ""
    raw_path = ""
    for u in updates:
        if u.note_type == "source":
            source_note_path = u.path
        elif u.note_type == "raw_capture":
            raw_path = u.path

    source_repo.upsert(
        ProcessedSource(
            url=content.source.url,
            url_hash=content.url_hash or compute_url_hash(content.source.url),
            content_hash=content.content_hash or "",
            source_type=content.source.source_type.value,
            title=content.source.title,
            source_note_path=source_note_path,
            raw_capture_path=raw_path,
            raindrop_id=content.source.raindrop_id,
            status="completed",
        )
    )

    for u in updates:
        if u.note_type in ("source", "topic", "entity", "concept", "synthesis"):
            note_repo.upsert(
                VaultNoteMapping(
                    note_path=u.path,
                    note_type=u.note_type,
                    slug=slug if u.note_type == "source" else "",
                    title=content.source.title if u.note_type == "source" else "",
                    source_url=content.source.url if u.note_type == "source" else "",
                )
            )

    result = IngestResult(
        source_url=content.source.url,
        source_type=content.source.source_type.value,
        source_note_path=source_note_path,
        raw_capture_path=raw_path,
        topics_updated=[t.name for t in topics],
        entities_updated=[e.name for e in entities],
        concepts_updated=[c.name for c in concepts],
        vault_updates=updates,
        deduplicated=state.get("deduplicated", False),
    )

    append_ingest_log(vault_path, result)

    db.close()
    return {**state, "result": result}


def _route_after_dedup(state: IngestState) -> str:
    return "persist_duplicate" if state.get("deduplicated") else "analyse"


def build_ingest_graph() -> StateGraph:
    graph = StateGraph(IngestState)

    graph.add_node("fetch", _fetch_content)
    graph.add_node("dedup", _check_dedup)
    graph.add_node("persist_duplicate", _persist_duplicate)
    graph.add_node("analyse", _analyse_content)
    graph.add_node("extract_knowledge", _extract_knowledge)
    graph.add_node("write_vault", _write_vault)
    graph.add_node("persist", _persist_state)

    graph.set_entry_point("fetch")
    graph.add_edge("fetch", "dedup")
    graph.add_conditional_edges(
        "dedup",
        _route_after_dedup,
        {
            "persist_duplicate": "persist_duplicate",
            "analyse": "analyse",
        },
    )
    graph.add_edge("persist_duplicate", END)
    graph.add_edge("analyse", "extract_knowledge")
    graph.add_edge("extract_knowledge", "write_vault")
    graph.add_edge("write_vault", "persist")
    graph.add_edge("persist", END)

    return graph


_compiled_graph = None


def get_ingest_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_ingest_graph().compile()
    return _compiled_graph
