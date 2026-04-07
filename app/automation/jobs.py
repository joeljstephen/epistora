"""Individual automation jobs that can be executed by the worker."""

from __future__ import annotations

import logging
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)


async def run_sync_job(limit: int | None = None) -> dict:
    """Run one Raindrop sync cycle, returning a summary dict."""
    from app.services.ingest_service import sync_raindrop

    settings = get_settings()
    batch_limit = limit or settings.sync_batch_limit

    logger.info("Sync job starting (limit=%d)", batch_limit)
    try:
        results = await sync_raindrop(limit=batch_limit)
        ingested = sum(1 for r in results if not r.deduplicated and not r.errors)
        skipped = sum(1 for r in results if r.deduplicated)
        failed = sum(1 for r in results if r.errors)
        summary = {
            "status": "ok",
            "total": len(results),
            "ingested": ingested,
            "skipped": skipped,
            "failed": failed,
        }
        logger.info("Sync job complete: %s", summary)
        return summary
    except Exception as exc:
        logger.error("Sync job failed: %s", exc)
        return {"status": "error", "error": str(exc)}


async def run_lint_job() -> dict:
    """Run one lint cycle, returning a summary dict."""
    from app.services.lint_service import lint_vault

    logger.info("Lint job starting")
    try:
        result = await lint_vault()
        summary = {
            "status": "ok",
            "total_notes": result.total_notes,
            "issues": len(result.issues),
            "report_path": result.report_path,
        }
        logger.info("Lint job complete: %s", summary)
        return summary
    except Exception as exc:
        logger.error("Lint job failed: %s", exc)
        return {"status": "error", "error": str(exc)}


async def run_rebuild_indexes_job() -> dict:
    """Rebuild all vault index files."""
    from app.vault.index_updater import rebuild_indexes

    settings = get_settings()
    vault_path = Path(settings.vault_path)

    logger.info("Index rebuild job starting")
    try:
        updated = rebuild_indexes(vault_path)
        summary = {
            "status": "ok",
            "indexes_updated": len(updated),
            "paths": [str(p) for p in updated],
        }
        logger.info("Index rebuild complete: %s", summary)
        return summary
    except Exception as exc:
        logger.error("Index rebuild failed: %s", exc)
        return {"status": "error", "error": str(exc)}
