"""Tests for the automation subsystem: scheduler, locks, jobs, worker."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.automation.locks import FileLock
from app.automation.scheduler import IntervalScheduler, ScheduledJob

# ---------------------------------------------------------------------------
# FileLock
# ---------------------------------------------------------------------------


class TestFileLock:
    def test_acquire_and_release(self, tmp_path: Path):
        lock = FileLock(tmp_path, "test-job")
        assert lock.acquire() is True
        lock.release()

    def test_double_acquire_fails(self, tmp_path: Path):
        lock1 = FileLock(tmp_path, "test-job")
        lock2 = FileLock(tmp_path, "test-job")
        assert lock1.acquire() is True
        assert lock2.acquire() is False
        lock1.release()
        assert lock2.acquire() is True
        lock2.release()

    def test_context_manager(self, tmp_path: Path):
        with FileLock(tmp_path, "ctx-test"):
            lock2 = FileLock(tmp_path, "ctx-test")
            assert lock2.acquire() is False

    def test_release_on_del(self, tmp_path: Path):
        lock = FileLock(tmp_path, "del-test")
        lock.acquire()
        del lock
        lock2 = FileLock(tmp_path, "del-test")
        assert lock2.acquire() is True
        lock2.release()

    def test_failed_acquire_closes_fd(self, tmp_path: Path):
        with (
            patch("os.open", return_value=123),
            patch("fcntl.flock", side_effect=BlockingIOError),
            patch("os.close") as mock_close,
        ):
            lock = FileLock(tmp_path, "close-test")
            assert lock.acquire() is False

        mock_close.assert_called_once_with(123)


# ---------------------------------------------------------------------------
# IntervalScheduler
# ---------------------------------------------------------------------------


class TestIntervalScheduler:
    @pytest.mark.asyncio
    async def test_runs_due_jobs(self):
        fn = AsyncMock(return_value={"status": "ok"})
        job = ScheduledJob(
            name="test-job",
            interval_seconds=0,
            fn=fn,
            enabled=True,
            last_run=0.0,
        )
        scheduler = IntervalScheduler()
        scheduler.register(job)

        results = await scheduler.tick()
        assert len(results) == 1
        assert results[0]["status"] == "ok"
        assert fn.call_count == 1
        assert job.run_count == 1

    @pytest.mark.asyncio
    async def test_skips_disabled_jobs(self):
        fn = AsyncMock(return_value={"status": "ok"})
        job = ScheduledJob(
            name="disabled-job",
            interval_seconds=0,
            fn=fn,
            enabled=False,
        )
        scheduler = IntervalScheduler()
        scheduler.register(job)

        results = await scheduler.tick()
        assert len(results) == 0
        assert fn.call_count == 0

    @pytest.mark.asyncio
    async def test_respects_interval(self):
        fn = AsyncMock(return_value={"status": "ok"})
        job = ScheduledJob(
            name="interval-job",
            interval_seconds=9999,
            fn=fn,
            enabled=True,
            last_run=time.monotonic(),
        )
        scheduler = IntervalScheduler()
        scheduler.register(job)

        results = await scheduler.tick()
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_handles_job_error(self):
        fn = AsyncMock(side_effect=RuntimeError("boom"))
        job = ScheduledJob(
            name="error-job",
            interval_seconds=0,
            fn=fn,
            enabled=True,
            last_run=0.0,
        )
        scheduler = IntervalScheduler()
        scheduler.register(job)

        results = await scheduler.tick()
        assert len(results) == 1
        assert results[0]["status"] == "error"
        assert "boom" in results[0]["error"]

    def test_status_report(self):
        fn = AsyncMock(return_value={})
        scheduler = IntervalScheduler()
        scheduler.register(ScheduledJob(name="j1", interval_seconds=60, fn=fn, enabled=True))
        scheduler.register(ScheduledJob(name="j2", interval_seconds=120, fn=fn, enabled=False))

        status = scheduler.status()
        assert len(status) == 2
        assert status[0]["name"] == "j1"
        assert status[0]["enabled"] is True
        assert status[1]["enabled"] is False


# ---------------------------------------------------------------------------
# Jobs (mocked service layer)
# ---------------------------------------------------------------------------


class TestSyncJob:
    @pytest.mark.asyncio
    async def test_sync_job_success(self):
        from app.models.results import IngestResult

        mock_results = [
            IngestResult(source_url="https://a.com"),
            IngestResult(source_url="https://b.com", deduplicated=True),
        ]

        with patch(
            "app.services.ingest_service.sync_raindrop",
            new_callable=AsyncMock,
            return_value=mock_results,
        ):
            from app.automation.jobs import run_sync_job

            result = await run_sync_job(limit=10)

        assert result["status"] == "ok"
        assert result["ingested"] == 1
        assert result["skipped"] == 1

    @pytest.mark.asyncio
    async def test_sync_job_error(self):
        with patch(
            "app.services.ingest_service.sync_raindrop",
            new_callable=AsyncMock,
            side_effect=ValueError("no token"),
        ):
            from app.automation.jobs import run_sync_job

            result = await run_sync_job()

        assert result["status"] == "error"
        assert "no token" in result["error"]


class TestLintJob:
    @pytest.mark.asyncio
    async def test_lint_job_success(self):
        from app.models.results import LintResult

        mock_result = LintResult(total_notes=5, issues=[], report_path="lint-log.md")

        with patch(
            "app.services.lint_service.lint_vault",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            from app.automation.jobs import run_lint_job

            result = await run_lint_job()

        assert result["status"] == "ok"
        assert result["total_notes"] == 5


class TestRebuildIndexesJob:
    @pytest.mark.asyncio
    async def test_rebuild_indexes_success(self, tmp_vault: Path):
        with (
            patch("app.config.get_settings") as mock_settings,
            patch(
                "app.vault.index_updater.rebuild_indexes",
                return_value=["INDEX.md", "TOPICS.md"],
            ),
        ):
            mock_settings.return_value.vault_path = tmp_vault
            mock_settings.return_value.db_path = tmp_vault / "data" / "app.db"

            from app.automation.jobs import run_rebuild_indexes_job

            result = await run_rebuild_indexes_job()

        assert result["status"] == "ok"
        assert result["indexes_updated"] == 2
