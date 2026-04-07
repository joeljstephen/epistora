"""Background automation worker — the main loop for ``kb worker``."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from app.automation.jobs import run_lint_job, run_rebuild_indexes_job, run_sync_job
from app.automation.locks import FileLock
from app.automation.scheduler import IntervalScheduler, ScheduledJob
from app.config import get_settings

logger = logging.getLogger(__name__)

TICK_INTERVAL = 5  # seconds between scheduler ticks


def _build_scheduler() -> IntervalScheduler:
    settings = get_settings()
    scheduler = IntervalScheduler()

    scheduler.register(
        ScheduledJob(
            name="raindrop_sync",
            interval_seconds=settings.sync_interval_seconds,
            fn=run_sync_job,
            enabled=settings.sync_enabled,
        )
    )
    scheduler.register(
        ScheduledJob(
            name="auto_lint",
            interval_seconds=settings.auto_lint_interval_seconds,
            fn=run_lint_job,
            enabled=settings.auto_lint_enabled,
        )
    )
    scheduler.register(
        ScheduledJob(
            name="rebuild_indexes",
            interval_seconds=settings.auto_rebuild_indexes_interval_seconds,
            fn=run_rebuild_indexes_job,
            enabled=settings.auto_rebuild_indexes_enabled,
        )
    )
    return scheduler


async def run_worker() -> None:
    """Main worker loop. Runs until interrupted."""
    settings = get_settings()
    lock_dir = settings.db_path.parent
    lock = FileLock(lock_dir, "epistora-worker")

    if not lock.acquire():
        logger.error("Another worker is already running. Exiting.")
        sys.exit(1)

    logger.info("Epistora worker starting")

    shutdown_event = asyncio.Event()

    def _signal_handler(*_):
        logger.info("Shutdown signal received")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    scheduler = _build_scheduler()

    enabled_jobs = [j for j in scheduler._jobs if j.enabled]
    if not enabled_jobs:
        logger.warning("No jobs are enabled. Worker will idle. Enable at least SYNC_ENABLED=true.")

    # Run first tick immediately for jobs that haven't run yet
    for job in scheduler._jobs:
        if job.enabled:
            job.last_run = 0.0

    try:
        while not shutdown_event.is_set():
            results = await scheduler.tick()
            for r in results:
                logger.info("Job result: %s", r)

            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=TICK_INTERVAL)
            except asyncio.TimeoutError:
                pass
    finally:
        lock.release()
        logger.info("Worker shut down cleanly")
