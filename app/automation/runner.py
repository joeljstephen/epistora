"""One-shot automation runner — the main building block for scheduler integration."""

from __future__ import annotations

import logging

from app.automation.discovery import discover_new_items
from app.automation.models import AutomationMode, AutomationRun
from app.automation.processing import process_pending_items
from app.automation.queue_store import AutomationRunRepository, QueueRepository
from app.config import get_settings
from app.storage.sqlite import Database
from app.utils.dates import utcnow

logger = logging.getLogger(__name__)


async def run_discover(
    connector_id: str = "raindrop",
    limit: int | None = None,
) -> dict:
    """Discover and queue new bookmarks from configured connectors."""
    result = await discover_new_items(connector_id=connector_id, limit=limit)
    return result.model_dump()


async def run_process_pending(
    mode: str = AutomationMode.SAFE,
    limit: int | None = None,
    retry_failed: bool = False,
    connector_id: str | None = None,
) -> dict:
    """Process pending items in the queue."""
    results = await process_pending_items(
        mode=mode,
        limit=limit,
        retry_failed=retry_failed,
        connector_id=connector_id,
    )

    succeeded = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)

    return {
        "status": "ok",
        "mode": mode,
        "processed": len(results),
        "succeeded": succeeded,
        "failed": failed,
        "results": [r.model_dump() for r in results],
    }


async def run_maintenance(
    run_lint: bool | None = None,
    run_rebuild: bool | None = None,
) -> dict:
    """Run optional maintenance tasks."""
    settings = get_settings()
    do_lint = run_lint if run_lint is not None else settings.automation_run_lint
    do_rebuild = (
        run_rebuild if run_rebuild is not None else settings.automation_run_rebuild_indexes
    )

    results = {}

    if do_lint:
        from app.automation.jobs import run_lint_job

        results["lint"] = await run_lint_job()

    if do_rebuild:
        from app.automation.jobs import run_rebuild_indexes_job

        results["rebuild_indexes"] = await run_rebuild_indexes_job()

    results["status"] = "ok"
    return results


async def run_automation(
    mode: str | None = None,
    limit: int | None = None,
    connector_id: str = "raindrop",
    run_maintenance_tasks: bool = True,
    retry_failed: bool = False,
) -> dict:
    """One-shot end-to-end automation: discover + process + optional maintenance.

    This is the primary entry point for cross-platform scheduler integration.
    """
    settings = get_settings()
    effective_mode = mode or settings.automation_default_mode

    # Record the run
    db = Database(settings.db_path)
    db.connect()
    try:
        run_repo = AutomationRunRepository(db)
        run_record = AutomationRun(
            run_type="full",
            mode=effective_mode,
            started_at=utcnow(),
        )
        run_id = run_repo.insert(run_record)
    finally:
        db.close()

    summary = {
        "mode": effective_mode,
        "discover": {},
        "process": {},
        "maintenance": {},
        "error": "",
    }

    try:
        # Step 1: Discover
        logger.info("Automation run: discover (connector=%s)", connector_id)
        discover_result = await run_discover(
            connector_id=connector_id, limit=limit
        )
        summary["discover"] = discover_result
        run_record.items_discovered = discover_result.get("items_discovered", 0)

        # Step 2: Process pending
        logger.info("Automation run: process (mode=%s)", effective_mode)
        process_result = await run_process_pending(
            mode=effective_mode,
            limit=limit,
            retry_failed=retry_failed,
            connector_id=None,  # Process all connectors
        )
        summary["process"] = process_result
        run_record.items_processed = process_result.get("succeeded", 0)
        run_record.items_failed = process_result.get("failed", 0)

        # Step 3: Maintenance
        if run_maintenance_tasks:
            logger.info("Automation run: maintenance")
            maint_result = await run_maintenance()
            summary["maintenance"] = maint_result
            run_record.maintenance_ran = True

        summary["status"] = "ok"

    except Exception as exc:
        logger.error("Automation run failed: %s", exc)
        summary["error"] = str(exc)
        summary["status"] = "error"
        run_record.error = str(exc)[:500]

    # Update the run record
    run_record.finished_at = utcnow()
    run_record.summary = (
        f"discover={run_record.items_discovered} "
        f"process={run_record.items_processed} "
        f"failed={run_record.items_failed}"
    )

    db = Database(settings.db_path)
    db.connect()
    try:
        run_repo = AutomationRunRepository(db)
        run_repo.update(run_id, run_record)
    finally:
        db.close()

    return summary


async def get_automation_status() -> dict:
    """Get comprehensive automation system status."""
    settings = get_settings()

    db = Database(settings.db_path)
    db.connect()
    try:
        queue_repo = QueueRepository(db)
        run_repo = AutomationRunRepository(db)

        queue_counts = queue_repo.count_by_status()
        last_run = run_repo.latest()

        # Get connector info
        from app.connectors.registry import build_inbox_connectors
        from app.storage.repositories import SyncCursorRepository

        connectors = build_inbox_connectors(settings)
        cursor_repo = SyncCursorRepository(db)

        connector_info = {}
        for cid, conn in connectors.items():
            cursor = cursor_repo.get(cid)
            connector_info[cid] = {
                "configured": True,
                "last_sync_at": cursor.last_sync_at.isoformat() if cursor else None,
            }

        # Backend availability
        from app.backends.models import TaskName
        from app.compiler.llm import get_backend_router

        router = get_backend_router()
        backends = {}
        for desc in router.describe_all(TaskName.INGEST):
            backends[desc.backend_type] = desc.available

        retryable = queue_counts.get("retryable_failed", 0)

        return {
            "automation_enabled": settings.automation_enabled,
            "default_mode": settings.automation_default_mode,
            "connectors": connector_info,
            "queue_counts": queue_counts,
            "total_queued": sum(queue_counts.values()),
            "retryable_failures": retryable,
            "last_run": last_run.model_dump() if last_run else None,
            "backends_available": backends,
            "settings": {
                "discover_batch_limit": settings.automation_discover_batch_limit,
                "process_limit": settings.automation_process_limit,
                "deep_enrich_limit_per_run": settings.automation_deep_enrich_limit_per_run,
                "deep_enrich_limit_per_day": settings.automation_deep_enrich_limit_per_day,
                "retry_max_attempts": settings.automation_retry_max_attempts,
                "run_lint": settings.automation_run_lint,
                "run_rebuild_indexes": settings.automation_run_rebuild_indexes,
            },
        }

    finally:
        db.close()
