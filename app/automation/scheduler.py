"""Interval-based scheduler for recurring automation jobs."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)


@dataclass
class ScheduledJob:
    name: str
    interval_seconds: int
    fn: Callable[[], Awaitable[dict]]
    enabled: bool = True
    last_run: float = 0.0
    run_count: int = 0
    last_result: dict = field(default_factory=dict)

    def is_due(self) -> bool:
        if not self.enabled:
            return False
        return (time.monotonic() - self.last_run) >= self.interval_seconds

    def mark_run(self, result: dict) -> None:
        self.last_run = time.monotonic()
        self.run_count += 1
        self.last_result = result


class IntervalScheduler:
    """Runs registered jobs on fixed intervals, with overlap prevention."""

    def __init__(self):
        self._jobs: list[ScheduledJob] = []
        self._running: set[str] = set()

    def register(self, job: ScheduledJob) -> None:
        self._jobs.append(job)
        logger.info(
            "Registered job '%s': interval=%ds, enabled=%s",
            job.name, job.interval_seconds, job.enabled,
        )

    async def tick(self) -> list[dict]:
        """Check all jobs and run any that are due. Returns summaries."""
        results = []
        for job in self._jobs:
            if not job.is_due():
                continue
            if job.name in self._running:
                logger.debug("Skipping '%s' — still running from previous tick", job.name)
                continue

            self._running.add(job.name)
            try:
                logger.info("Running scheduled job '%s'", job.name)
                result = await job.fn()
                job.mark_run(result)
                results.append({"job": job.name, **result})
            except Exception as exc:
                logger.error("Job '%s' raised: %s", job.name, exc)
                job.mark_run({"status": "error", "error": str(exc)})
                results.append({"job": job.name, "status": "error", "error": str(exc)})
            finally:
                self._running.discard(job.name)

        return results

    def status(self) -> list[dict]:
        return [
            {
                "name": j.name,
                "enabled": j.enabled,
                "interval_seconds": j.interval_seconds,
                "run_count": j.run_count,
                "last_result": j.last_result,
                "is_running": j.name in self._running,
            }
            for j in self._jobs
        ]
