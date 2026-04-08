"""Automation status and control API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.auth import require_api_key
from app.automation.jobs import run_lint_job, run_rebuild_indexes_job, run_sync_job
from app.automation.runner import (
    get_automation_status,
    run_automation,
    run_discover,
    run_process_pending,
)
from app.backends.models import TaskName
from app.compiler.llm import get_backend_router
from app.config import get_settings

router = APIRouter(
    prefix="/automation",
    tags=["automation"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/status")
async def automation_status():
    """Return current automation configuration, queue status, and backend availability."""
    settings = get_settings()
    router_instance = get_backend_router()

    backend_status = {}
    for task in TaskName:
        backend_status[task.value] = [d.model_dump() for d in router_instance.describe_all(task)]

    # Include queue-based automation status
    queue_status = await get_automation_status()

    return {
        # Legacy fields for backward compatibility
        "sync_enabled": settings.sync_enabled,
        "sync_interval_seconds": settings.sync_interval_seconds,
        "auto_lint_enabled": settings.auto_lint_enabled,
        "auto_lint_interval_seconds": settings.auto_lint_interval_seconds,
        "auto_rebuild_indexes_enabled": settings.auto_rebuild_indexes_enabled,
        "auto_rebuild_indexes_interval_seconds": settings.auto_rebuild_indexes_interval_seconds,
        "backends": backend_status,
        # New queue-based automation fields
        "queue": queue_status,
    }


@router.post("/discover")
async def trigger_discover(connector_id: str = "raindrop", limit: int = 25):
    """Discover and queue new bookmarks."""
    return await run_discover(connector_id=connector_id, limit=limit)


@router.post("/process-pending")
async def trigger_process_pending(
    mode: str = "safe",
    limit: int = 10,
    retry_failed: bool = False,
):
    """Process pending queued items."""
    return await run_process_pending(
        mode=mode, limit=limit, retry_failed=retry_failed
    )


@router.post("/run-pending")
async def trigger_run_pending(
    mode: str = "safe",
    limit: int | None = None,
    connector_id: str = "raindrop",
):
    """One-shot end-to-end: discover + process + maintenance."""
    return await run_automation(
        mode=mode, limit=limit, connector_id=connector_id
    )


# Legacy endpoints kept for backward compatibility
@router.post("/run-sync")
async def trigger_sync(limit: int = 25):
    """Trigger a one-off inbox sync (legacy)."""
    return await run_sync_job(limit=limit)


@router.post("/run-lint")
async def trigger_lint():
    """Trigger a one-off vault lint."""
    return await run_lint_job()


@router.post("/rebuild-indexes")
async def trigger_rebuild_indexes():
    """Trigger an index rebuild."""
    return await run_rebuild_indexes_job()
