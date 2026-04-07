"""Automation status and control API endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.automation.jobs import run_lint_job, run_rebuild_indexes_job, run_sync_job
from app.backends.models import TaskName
from app.compiler.llm import get_backend_router
from app.config import get_settings

router = APIRouter(prefix="/automation", tags=["automation"])


@router.get("/status")
async def automation_status():
    """Return current automation configuration and backend availability."""
    settings = get_settings()
    router_instance = get_backend_router()

    backend_status = {}
    for task in TaskName:
        backend_status[task.value] = [d.model_dump() for d in router_instance.describe_all(task)]

    return {
        "sync_enabled": settings.sync_enabled,
        "sync_interval_seconds": settings.sync_interval_seconds,
        "auto_lint_enabled": settings.auto_lint_enabled,
        "auto_lint_interval_seconds": settings.auto_lint_interval_seconds,
        "auto_rebuild_indexes_enabled": settings.auto_rebuild_indexes_enabled,
        "auto_rebuild_indexes_interval_seconds": settings.auto_rebuild_indexes_interval_seconds,
        "backends": backend_status,
    }


@router.post("/run-sync")
async def trigger_sync(limit: int = 25):
    """Trigger a one-off Raindrop sync."""
    return await run_sync_job(limit=limit)


@router.post("/run-lint")
async def trigger_lint():
    """Trigger a one-off vault lint."""
    return await run_lint_job()


@router.post("/rebuild-indexes")
async def trigger_rebuild_indexes():
    """Trigger an index rebuild."""
    return await run_rebuild_indexes_job()
