"""One-shot automation runner — the main building block for scheduler integration."""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

from app.automation.discovery import discover_new_items
from app.automation.models import AutomationMode, AutomationRun
from app.automation.processing import process_pending_items
from app.automation.queue_store import AutomationRunRepository, QueueRepository
from app.config import get_settings
from app.events import EventType, publish
from app.maintenance.service import maintain_vault
from app.storage.sqlite import Database
from app.utils.dates import utcnow

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, dict[str, Any]], None]
_PERSONAL_LEARNING_PROMPT_PROFILE = "personal_learning"


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
        logger.debug("Automation progress callback failed for stage=%s", stage, exc_info=True)


@contextmanager
def _temporary_prompt_profile(profile: str):
    previous = os.environ.get("EPISTORA_PROMPT_PROFILE")
    os.environ["EPISTORA_PROMPT_PROFILE"] = profile
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("EPISTORA_PROMPT_PROFILE", None)
        else:
            os.environ["EPISTORA_PROMPT_PROFILE"] = previous


async def run_discover(
    connector_id: str = "raindrop",
    limit: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    """Discover and queue new bookmarks from configured connectors."""
    result = await discover_new_items(
        connector_id=connector_id,
        limit=limit,
        progress_callback=progress_callback,
    )
    return result.model_dump()


async def run_process_pending(
    mode: str = AutomationMode.SAFE,
    limit: int | None = None,
    retry_failed: bool = False,
    connector_id: str | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    """Process pending items in the queue."""
    results = await process_pending_items(
        mode=mode,
        limit=limit,
        retry_failed=retry_failed,
        connector_id=connector_id,
        progress_callback=progress_callback,
    )

    succeeded = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)

    return {
        "status": "ok",
        "mode": mode,
        "processed": len(results),
        "succeeded": succeeded,
        "failed": failed,
        "changed_paths": sorted(
            {
                path
                for result in results
                for path in result.changed_paths
                if path.endswith(".md")
            }
        ),
        "results": [r.model_dump() for r in results],
    }


async def run_maintenance(
    run_lint: bool | None = None,
    run_rebuild: bool | None = None,
    mode: str | None = None,
    scope_paths: list[str] | None = None,
) -> dict:
    """Run optional maintenance tasks."""
    settings = get_settings()
    effective_mode = mode or settings.automation_default_mode
    do_lint = run_lint if run_lint is not None else settings.automation_run_lint
    do_rebuild = (
        run_rebuild if run_rebuild is not None else settings.automation_run_rebuild_indexes
    )
    publish(
        EventType.SCHEDULED_MAINTENANCE_TICK,
        mode=effective_mode,
        scope_paths=scope_paths or [],
        force_rebuild=bool(do_rebuild),
    )

    maintenance = await maintain_vault(
        vault_path=settings.vault_path,
        mode=effective_mode,
        scope_paths=scope_paths,
        force_rebuild=bool(do_rebuild),
    )

    results = maintenance.model_dump()
    results["status"] = "ok"
    for task_result in maintenance.task_results:
        if task_result.task_name == "structural_repair":
            results["rebuild_indexes"] = {
                "status": task_result.status,
                "indexes_updated": task_result.details.get("indexes_updated", 0),
                "paths": task_result.changed_paths,
            }
            break

    if do_lint:
        from app.automation.jobs import run_lint_job

        results["lint"] = await run_lint_job()

    return results


async def run_automation(
    mode: str | None = None,
    limit: int | None = None,
    connector_id: str = "raindrop",
    run_maintenance_tasks: bool = True,
    retry_failed: bool = False,
    progress_callback: ProgressCallback | None = None,
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
        _emit_progress(progress_callback, "automation_stage", stage_name="discover")
        discover_result = await run_discover(
            connector_id=connector_id, limit=limit, progress_callback=progress_callback
        )
        summary["discover"] = discover_result
        run_record.items_discovered = discover_result.get("items_discovered", 0)

        # Step 2: Process pending
        logger.info("Automation run: process (mode=%s)", effective_mode)
        _emit_progress(progress_callback, "automation_stage", stage_name="process")
        process_result = await run_process_pending(
            mode=effective_mode,
            limit=limit,
            retry_failed=retry_failed,
            connector_id=None,  # Process all connectors
            progress_callback=progress_callback,
        )
        summary["process"] = process_result
        run_record.items_processed = process_result.get("succeeded", 0)
        run_record.items_failed = process_result.get("failed", 0)

        # Step 3: Maintenance
        if run_maintenance_tasks:
            logger.info("Automation run: maintenance")
            _emit_progress(progress_callback, "automation_stage", stage_name="maintenance")
            changed_paths = process_result.get("changed_paths", [])
            maint_result = await run_maintenance(
                mode=effective_mode,
                scope_paths=changed_paths,
            )
            summary["maintenance"] = maint_result
            run_record.maintenance_ran = True

        summary["status"] = "ok"
        _emit_progress(progress_callback, "automation_done", mode=effective_mode)

    except Exception as exc:
        logger.error("Automation run failed: %s", exc)
        summary["error"] = str(exc)
        summary["status"] = "error"
        run_record.error = str(exc)[:500]
        _emit_progress(progress_callback, "automation_failed", error=str(exc))

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


def _refresh_personal_learning_read_model(
    *,
    vault_path: Path,
    changed_paths: list[str],
    mode: str,
) -> dict:
    from app.read_model.store import ReadModelStore

    store = ReadModelStore(vault_path)
    normalized_paths = sorted({path for path in changed_paths if path.endswith(".md")})
    if mode == AutomationMode.DEEP or not normalized_paths:
        details = store.rebuild()
        return {"status": "full_rebuild", **details}
    details = store.refresh_paths(normalized_paths)
    return {"status": str(details.get("mode", "incremental")), **details}


async def run_personal_learning(
    mode: str = AutomationMode.BALANCED,
    limit: int | None = None,
    connector_id: str = "raindrop",
    run_maintenance_tasks: bool = True,
    retry_failed: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    """Run the composed personal-learning preset workflow."""
    from app.services.review_service import generate_daily_digest, generate_weekly_digest
    from app.vault.index_updater import rebuild_indexes

    settings = get_settings()
    effective_mode = mode or AutomationMode.BALANCED
    vault_path = Path(settings.vault_path)

    db = Database(settings.db_path)
    db.connect()
    try:
        run_repo = AutomationRunRepository(db)
        run_record = AutomationRun(
            run_type="personal_learning",
            mode=effective_mode,
            started_at=utcnow(),
        )
        run_id = run_repo.insert(run_record)
    finally:
        db.close()

    summary = {
        "preset": "personal_learning",
        "prompt_profile": _PERSONAL_LEARNING_PROMPT_PROFILE,
        "mode": effective_mode,
        "discover": {},
        "process": {},
        "read_model": {},
        "views": {},
        "reviews": {},
        "maintenance": {},
        "error": "",
    }

    try:
        logger.info("Personal learning run: discover (connector=%s)", connector_id)
        _emit_progress(progress_callback, "automation_stage", stage_name="discover")
        discover_result = await run_discover(
            connector_id=connector_id,
            limit=limit,
            progress_callback=progress_callback,
        )
        summary["discover"] = discover_result
        run_record.items_discovered = discover_result.get("items_discovered", 0)

        logger.info("Personal learning run: process (mode=%s)", effective_mode)
        _emit_progress(progress_callback, "automation_stage", stage_name="process")
        with _temporary_prompt_profile(_PERSONAL_LEARNING_PROMPT_PROFILE):
            process_result = await run_process_pending(
                mode=effective_mode,
                limit=limit,
                retry_failed=retry_failed,
                connector_id=None,
                progress_callback=progress_callback,
            )
        summary["process"] = process_result
        run_record.items_processed = process_result.get("succeeded", 0)
        run_record.items_failed = process_result.get("failed", 0)

        changed_paths = process_result.get("changed_paths", [])

        logger.info("Personal learning run: read-model refresh")
        _emit_progress(progress_callback, "automation_stage", stage_name="read_model")
        read_model_result = _refresh_personal_learning_read_model(
            vault_path=vault_path,
            changed_paths=changed_paths,
            mode=effective_mode,
        )
        summary["read_model"] = read_model_result

        logger.info("Personal learning run: view rebuild")
        _emit_progress(progress_callback, "automation_stage", stage_name="views")
        updated_views = rebuild_indexes(vault_path)
        summary["views"] = {
            "status": "ok",
            "updated": updated_views,
            "count": len(updated_views),
        }

        logger.info("Personal learning run: review evaluation")
        _emit_progress(progress_callback, "automation_stage", stage_name="reviews")
        daily_result = await generate_daily_digest()
        weekly_result = await generate_weekly_digest()
        summary["reviews"] = {
            "daily": daily_result.model_dump(),
            "weekly": weekly_result.model_dump(),
        }

        if run_maintenance_tasks:
            logger.info("Personal learning run: maintenance")
            _emit_progress(progress_callback, "automation_stage", stage_name="maintenance")
            maint_result = await run_maintenance(
                mode=effective_mode,
                scope_paths=changed_paths,
            )
            summary["maintenance"] = maint_result
            run_record.maintenance_ran = True

        summary["status"] = "ok"
        _emit_progress(progress_callback, "automation_done", mode=effective_mode)

    except Exception as exc:
        logger.error("Personal learning run failed: %s", exc)
        summary["error"] = str(exc)
        summary["status"] = "error"
        run_record.error = str(exc)[:500]
        _emit_progress(progress_callback, "automation_failed", error=str(exc))

    run_record.finished_at = utcnow()
    run_record.summary = (
        f"discover={run_record.items_discovered} "
        f"process={run_record.items_processed} "
        f"failed={run_record.items_failed} "
        f"views={summary.get('views', {}).get('count', 0)}"
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
