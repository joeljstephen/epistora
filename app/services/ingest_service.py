"""High-level ingest service — coordinates direct URL and inbox ingestion."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.compiler.ingest_graph import get_ingest_graph
from app.config import get_settings
from app.connectors.classifier import classify_url
from app.connectors.registry import get_inbox_connector
from app.models.db import SyncCursor
from app.models.results import IngestResult
from app.models.source import SourceItem
from app.storage.repositories import SourceRepository, SyncCursorRepository
from app.storage.sqlite import Database
from app.utils.hashing import url_hash
from app.utils.http import assert_safe_http_url

logger = logging.getLogger(__name__)


async def ingest_url(url: str) -> IngestResult:
    """Ingest a single URL into the vault."""
    settings = get_settings()
    assert_safe_http_url(url)

    db = Database(settings.db_path)
    db.connect()
    source_repo = SourceRepository(db)

    existing = source_repo.find_by_url_hash(url_hash(url))
    if existing and existing.status == "completed":
        logger.info("URL already ingested: %s", url)
        db.close()
        return IngestResult(
            source_url=url,
            source_type=existing.source_type,
            source_note_path=existing.source_note_path,
            deduplicated=True,
        )
    db.close()

    source_type = classify_url(url)
    item = SourceItem(url=url, source_type=source_type)

    graph = get_ingest_graph()
    final_state = await graph.ainvoke({"item": item})

    result = final_state.get("result")
    if result:
        return result

    return IngestResult(
        source_url=url,
        errors=["Ingest graph did not produce a result"],
    )


async def sync_inbox(connector_id: str = "raindrop", limit: int = 25) -> list[IngestResult]:
    """Sync recent items from a saved-link inbox connector and ingest them."""
    settings = get_settings()
    connector = get_inbox_connector(connector_id, settings)

    db = Database(settings.db_path)
    db.connect()
    cursor_repo = SyncCursorRepository(db)
    source_repo = SourceRepository(db)

    last_cursor = cursor_repo.get(connector.connector_id)
    since = last_cursor.last_sync_at if last_cursor else datetime(2020, 1, 1, tzinfo=timezone.utc)

    items = connector.fetch_since(since, limit=limit)
    logger.info(
        "Inbox sync found %d new items for connector=%s",
        len(items),
        connector.connector_id,
    )

    results: list[IngestResult] = []
    for item in items:
        existing = source_repo.find_by_url_hash(url_hash(item.url))
        if existing and existing.status == "completed":
            results.append(IngestResult(source_url=item.url, deduplicated=True))
            continue

        try:
            graph = get_ingest_graph()
            final_state = await graph.ainvoke({"item": item})
            result = final_state.get(
                "result", IngestResult(source_url=item.url, errors=["No result"])
            )
            results.append(result)
        except Exception as e:
            logger.error("Failed to ingest %s: %s", item.url, e)
            results.append(IngestResult(source_url=item.url, errors=[str(e)]))

    cursor_repo.upsert(SyncCursor(connector=connector.connector_id))
    db.close()

    return results


async def sync_raindrop(limit: int = 25) -> list[IngestResult]:
    """Backward-compatible alias for the generic inbox sync path."""
    return await sync_inbox(connector_id="raindrop", limit=limit)
