"""Discovery service — fetches new bookmarks and stages them in the queue."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from app.automation.models import DiscoverResult, QueuedItem, QueueItemStatus
from app.automation.queue_store import QueueRepository
from app.config import get_settings
from app.connectors.registry import get_inbox_connector
from app.storage.repositories import SourceRepository, SyncCursorRepository
from app.storage.sqlite import Database
from app.utils.hashing import url_hash

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, dict[str, Any]], None]


def _emit_progress(
    progress_callback: ProgressCallback | None,
    stage: str,
    **payload: Any,
) -> None:
    if progress_callback is None:
        return
    try:
        progress_callback(stage, payload)
    except Exception:
        logger.debug("Discovery progress callback failed for stage=%s", stage, exc_info=True)


async def discover_new_items(
    connector_id: str = "raindrop",
    limit: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> DiscoverResult:
    """Discover new bookmarks and stage them in the durable queue.

    The sync cursor is only advanced after items are durably staged.
    """
    settings = get_settings()
    batch_limit = limit or settings.automation_discover_batch_limit

    try:
        connector = get_inbox_connector(connector_id, settings)
    except ValueError as e:
        return DiscoverResult(connector_id=connector_id, error=str(e))

    db = Database(settings.db_path)
    db.connect()

    try:
        cursor_repo = SyncCursorRepository(db)
        source_repo = SourceRepository(db)
        queue_repo = QueueRepository(db)

        last_cursor = cursor_repo.get(connector.connector_id)
        since = (
            last_cursor.last_sync_at
            if last_cursor
            else datetime(2020, 1, 1, tzinfo=timezone.utc)
        )

        logger.info(
            "Discovering items for connector=%s since=%s limit=%d",
            connector_id,
            since.isoformat(),
            batch_limit,
        )

        _emit_progress(progress_callback, "discover_fetching", connector=connector_id, limit=batch_limit)
        items = connector.fetch_since(since, limit=batch_limit)
        _emit_progress(
            progress_callback,
            "discover_fetched",
            connector=connector_id,
            count=len(items),
        )
        logger.info("Fetched %d items from connector=%s", len(items), connector_id)

        discovered = 0
        skipped = 0
        latest_saved_at = since

        for item in items:
            uhash = url_hash(item.url)

            # Skip if already in queue (any status)
            existing_queued = queue_repo.find_by_url_hash(uhash)
            if existing_queued:
                skipped += 1
                _emit_progress(
                    progress_callback,
                    "discover_skipped",
                    title=item.title or item.url,
                    url=item.url,
                )
                if item.saved_at > latest_saved_at:
                    latest_saved_at = item.saved_at
                continue

            # Skip if already fully processed in processed_sources
            existing_source = source_repo.find_by_url_hash(uhash)
            if existing_source and existing_source.status == "completed":
                # Stage as skipped_duplicate so we don't re-fetch
                queue_repo.insert(
                    QueuedItem(
                        connector_id=connector_id,
                        external_id=item.external_id,
                        url=item.url,
                        url_hash=uhash,
                        title=item.title,
                        source_type=item.source_type.value,
                        tags=json.dumps(item.tags),
                        saved_at=item.saved_at,
                        status=QueueItemStatus.SKIPPED_DUPLICATE,
                        provider_metadata=item.provider_metadata,
                    )
                )
                skipped += 1
                _emit_progress(
                    progress_callback,
                    "discover_skipped",
                    title=item.title or item.url,
                    url=item.url,
                )
                if item.saved_at > latest_saved_at:
                    latest_saved_at = item.saved_at
                continue

            # Stage as discovered
            queue_repo.insert(
                QueuedItem(
                    connector_id=connector_id,
                    external_id=item.external_id,
                    url=item.url,
                    url_hash=uhash,
                    title=item.title,
                    source_type=item.source_type.value,
                    tags=json.dumps(item.tags),
                    saved_at=item.saved_at,
                    status=QueueItemStatus.DISCOVERED,
                    provider_metadata=item.provider_metadata,
                )
            )
            discovered += 1
            _emit_progress(
                progress_callback,
                "discover_queued",
                title=item.title or item.url,
                url=item.url,
            )
            if item.saved_at > latest_saved_at:
                latest_saved_at = item.saved_at

        # Advance cursor only after all items are durably staged
        if items:
            from app.models.db import SyncCursor

            cursor_repo.upsert(
                SyncCursor(
                    connector=connector.connector_id,
                    last_sync_at=latest_saved_at,
                )
            )
            logger.info(
                "Cursor advanced for connector=%s to %s",
                connector_id,
                latest_saved_at.isoformat(),
            )

        result = DiscoverResult(
            items_discovered=discovered,
            items_skipped_duplicate=skipped,
            connector_id=connector_id,
        )
        _emit_progress(
            progress_callback,
            "discover_done",
            connector=connector_id,
            discovered=discovered,
            skipped=skipped,
        )
        logger.info("Discovery complete: %s", result.model_dump())
        return result

    finally:
        db.close()
