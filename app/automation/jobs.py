"""Individual automation jobs that can be executed by the worker."""

from __future__ import annotations

import logging
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)


async def run_sync_job(limit: int | None = None) -> dict:
    """Run one inbox sync cycle, returning a summary dict."""
    from app.services.ingest_service import sync_inbox

    settings = get_settings()
    batch_limit = limit or settings.sync_batch_limit

    logger.info("Sync job starting (limit=%d)", batch_limit)
    try:
        results = await sync_inbox(limit=batch_limit)
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


async def run_review_daily_job(reference_date=None) -> dict:
    """Generate the daily review digest."""
    from app.services.review_service import generate_daily_digest

    logger.info("Daily review job starting")
    try:
        result = await generate_daily_digest(reference_date=reference_date)
        summary = result.model_dump()
        summary["status"] = "ok"
        logger.info("Daily review job complete: %s", summary)
        return summary
    except Exception as exc:
        logger.error("Daily review job failed: %s", exc)
        return {"status": "error", "error": str(exc)}


async def run_review_weekly_job(reference_date=None) -> dict:
    """Generate the weekly review digest."""
    from app.services.review_service import generate_weekly_digest

    logger.info("Weekly review job starting")
    try:
        result = await generate_weekly_digest(reference_date=reference_date)
        summary = result.model_dump()
        summary["status"] = "ok"
        logger.info("Weekly review job complete: %s", summary)
        return summary
    except Exception as exc:
        logger.error("Weekly review job failed: %s", exc)
        return {"status": "error", "error": str(exc)}
