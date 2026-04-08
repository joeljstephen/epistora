"""Tests for the queue-based automation system."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.automation.models import (
    AutomationMode,
    AutomationRun,
    FailureType,
    ItemAttempt,
    QueuedItem,
    QueueItemStatus,
)
from app.automation.processing import (
    classify_failure,
    compute_backoff,
    is_retryable,
)
from app.automation.queue_store import (
    AutomationRunRepository,
    ItemAttemptRepository,
    QueueRepository,
)


# ---------------------------------------------------------------------------
# QueueRepository
# ---------------------------------------------------------------------------


class TestQueueRepository:
    def test_insert_and_find(self, tmp_db):
        repo = QueueRepository(tmp_db)
        item = QueuedItem(
            connector_id="raindrop",
            external_id="123",
            url="https://example.com/article",
            url_hash="abc123",
            title="Test Article",
            source_type="article",
            tags=json.dumps(["test"]),
            saved_at=datetime.now(timezone.utc),
        )

        item_id = repo.insert(item)
        assert item_id > 0

        found = repo.find_by_url_hash("abc123")
        assert found is not None
        assert found.url == "https://example.com/article"
        assert found.title == "Test Article"
        assert found.connector_id == "raindrop"
        assert found.status == QueueItemStatus.DISCOVERED

    def test_find_by_connector_external(self, tmp_db):
        repo = QueueRepository(tmp_db)
        repo.insert(QueuedItem(
            connector_id="raindrop",
            external_id="456",
            url="https://example.com/page",
            url_hash="def456",
        ))

        found = repo.find_by_connector_external("raindrop", "456")
        assert found is not None
        assert found.external_id == "456"

        not_found = repo.find_by_connector_external("raindrop", "999")
        assert not_found is None

    def test_duplicate_detection(self, tmp_db):
        repo = QueueRepository(tmp_db)
        repo.insert(QueuedItem(
            url="https://example.com/dup",
            url_hash="dup123",
        ))

        found = repo.find_by_url_hash("dup123")
        assert found is not None

        # Different URL hash should not be found
        not_found = repo.find_by_url_hash("other_hash")
        assert not_found is None

    def test_get_pending(self, tmp_db):
        repo = QueueRepository(tmp_db)

        # Insert discovered items
        repo.insert(QueuedItem(url="https://a.com", url_hash="a1", status="discovered"))
        repo.insert(QueuedItem(url="https://b.com", url_hash="b1", status="discovered"))
        repo.insert(QueuedItem(url="https://c.com", url_hash="c1", status="completed"))
        repo.insert(QueuedItem(url="https://d.com", url_hash="d1", status="retryable_failed"))

        pending = repo.get_pending(limit=10)
        assert len(pending) == 2

        pending_with_retry = repo.get_pending(limit=10, include_retryable=True)
        assert len(pending_with_retry) == 3

    def test_get_pending_respects_limit(self, tmp_db):
        repo = QueueRepository(tmp_db)
        for i in range(5):
            repo.insert(QueuedItem(url=f"https://example.com/{i}", url_hash=f"hash{i}"))

        pending = repo.get_pending(limit=2)
        assert len(pending) == 2

    def test_get_pending_respects_next_attempt_at(self, tmp_db):
        repo = QueueRepository(tmp_db)

        # Item with future retry time — should NOT be returned
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        repo.insert(QueuedItem(
            url="https://future.com",
            url_hash="future1",
            status="retryable_failed",
            next_attempt_at=future,
        ))

        # Item with past retry time — should be returned
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        repo.insert(QueuedItem(
            url="https://past.com",
            url_hash="past1",
            status="retryable_failed",
            next_attempt_at=past,
        ))

        pending = repo.get_pending(limit=10, include_retryable=True)
        urls = [p.url for p in pending]
        assert "https://past.com" in urls
        assert "https://future.com" not in urls

    def test_update_status(self, tmp_db):
        repo = QueueRepository(tmp_db)
        item_id = repo.insert(QueuedItem(url="https://test.com", url_hash="test1"))

        repo.update_status(
            item_id,
            QueueItemStatus.COMPLETED,
            mode="safe",
            backend="none",
        )

        found = repo.find_by_url_hash("test1")
        assert found.status == QueueItemStatus.COMPLETED
        assert found.attempt_count == 1

    def test_mark_processing(self, tmp_db):
        repo = QueueRepository(tmp_db)
        item_id = repo.insert(QueuedItem(url="https://test.com", url_hash="proc1"))

        repo.mark_processing(item_id)

        found = repo.find_by_url_hash("proc1")
        assert found.status == QueueItemStatus.PROCESSING

    def test_count_by_status(self, tmp_db):
        repo = QueueRepository(tmp_db)
        repo.insert(QueuedItem(url="https://a.com", url_hash="s1", status="discovered"))
        repo.insert(QueuedItem(url="https://b.com", url_hash="s2", status="discovered"))
        repo.insert(QueuedItem(url="https://c.com", url_hash="s3", status="completed"))

        counts = repo.count_by_status()
        assert counts.get("discovered") == 2
        assert counts.get("completed") == 1

    def test_get_retryable_failed(self, tmp_db):
        repo = QueueRepository(tmp_db)
        repo.insert(QueuedItem(
            url="https://fail.com", url_hash="f1", status="retryable_failed"
        ))
        repo.insert(QueuedItem(
            url="https://ok.com", url_hash="ok1", status="completed"
        ))

        failed = repo.get_retryable_failed()
        assert len(failed) == 1
        assert failed[0].url == "https://fail.com"


# ---------------------------------------------------------------------------
# AutomationRunRepository
# ---------------------------------------------------------------------------


class TestAutomationRunRepository:
    def test_insert_and_latest(self, tmp_db):
        repo = AutomationRunRepository(tmp_db)
        run = AutomationRun(
            run_type="full",
            mode="safe",
            items_discovered=5,
            items_processed=3,
        )

        run_id = repo.insert(run)
        assert run_id > 0

        latest = repo.latest()
        assert latest is not None
        assert latest.run_type == "full"
        assert latest.items_discovered == 5

    def test_latest_by_type(self, tmp_db):
        repo = AutomationRunRepository(tmp_db)
        repo.insert(AutomationRun(run_type="discover", mode="safe"))
        repo.insert(AutomationRun(run_type="full", mode="balanced"))

        discover = repo.latest("discover")
        assert discover is not None
        assert discover.run_type == "discover"

        full = repo.latest("full")
        assert full is not None
        assert full.run_type == "full"

    def test_update(self, tmp_db):
        repo = AutomationRunRepository(tmp_db)
        run = AutomationRun(run_type="full", mode="safe")
        run_id = repo.insert(run)

        run.items_processed = 10
        run.finished_at = datetime.now(timezone.utc)
        run.summary = "done"
        repo.update(run_id, run)

        latest = repo.latest()
        assert latest.items_processed == 10
        assert latest.summary == "done"


# ---------------------------------------------------------------------------
# ItemAttemptRepository
# ---------------------------------------------------------------------------


class TestItemAttemptRepository:
    def test_insert_and_query(self, tmp_db):
        # First create a queue item
        queue_repo = QueueRepository(tmp_db)
        item_id = queue_repo.insert(QueuedItem(url="https://t.com", url_hash="t1"))

        attempt_repo = ItemAttemptRepository(tmp_db)
        attempt = ItemAttempt(
            queued_item_id=item_id,
            attempt_number=1,
            mode="safe",
            success=True,
        )
        attempt_repo.insert(attempt)

        attempts = attempt_repo.for_item(item_id)
        assert len(attempts) == 1
        assert attempts[0].success is True
        assert attempts[0].mode == "safe"


# ---------------------------------------------------------------------------
# Failure classification and retry logic
# ---------------------------------------------------------------------------


class TestFailureClassification:
    def test_timeout(self):
        assert classify_failure(TimeoutError("timed out")) == FailureType.TIMEOUT

    def test_network(self):
        assert classify_failure(ConnectionError("connection refused")) == FailureType.NETWORK

    def test_rate_limit(self):
        assert classify_failure(RuntimeError("429 too many requests")) == FailureType.RATE_LIMIT

    def test_extraction(self):
        assert classify_failure(RuntimeError("extract failed")) == FailureType.EXTRACTION

    def test_unsupported(self):
        assert classify_failure(RuntimeError("unsupported format")) == FailureType.UNSUPPORTED

    def test_unknown(self):
        assert classify_failure(RuntimeError("something weird")) == FailureType.UNKNOWN

    def test_retryable(self):
        assert is_retryable(FailureType.NETWORK) is True
        assert is_retryable(FailureType.TIMEOUT) is True
        assert is_retryable(FailureType.RATE_LIMIT) is True
        assert is_retryable(FailureType.UNSUPPORTED) is False


class TestBackoff:
    def test_exponential(self):
        t1 = compute_backoff(0, base_seconds=60)
        t2 = compute_backoff(1, base_seconds=60)
        t3 = compute_backoff(2, base_seconds=60)

        # The delays should increase
        now = datetime.now(timezone.utc)
        delta1 = (t1 - now).total_seconds()
        delta2 = (t2 - now).total_seconds()
        delta3 = (t3 - now).total_seconds()

        assert delta1 < delta2 < delta3
        assert delta1 >= 55  # ~60s base
        assert delta2 >= 115  # ~120s
        assert delta3 >= 235  # ~240s


# ---------------------------------------------------------------------------
# Discovery (mocked connector)
# ---------------------------------------------------------------------------


class TestDiscovery:
    @pytest.mark.asyncio
    async def test_discover_queues_items(self, tmp_db, tmp_vault):
        from app.automation.discovery import discover_new_items
        from app.models.source import SourceItem, SourceType

        mock_items = [
            SourceItem(
                url="https://example.com/new-article",
                title="New Article",
                source_type=SourceType.ARTICLE,
                tags=["test"],
                external_id="ext1",
                saved_at=datetime.now(timezone.utc),
            ),
        ]

        mock_connector = MagicMock()
        mock_connector.connector_id = "raindrop"
        mock_connector.fetch_since.return_value = mock_items

        with (
            patch("app.automation.discovery.get_settings") as mock_settings,
            patch("app.automation.discovery.get_inbox_connector", return_value=mock_connector),
            patch("app.automation.discovery.Database") as MockDB,
        ):
            mock_settings.return_value.automation_discover_batch_limit = 25
            mock_settings.return_value.db_path = tmp_db._path
            MockDB.return_value = tmp_db

            result = await discover_new_items(connector_id="raindrop")

        assert result.items_discovered == 1
        assert result.items_skipped_duplicate == 0

    @pytest.mark.asyncio
    async def test_discover_skips_duplicates(self, tmp_db, tmp_vault):
        from app.automation.discovery import discover_new_items
        from app.models.source import SourceItem, SourceType
        from app.utils.hashing import url_hash

        # Pre-insert an item in the queue
        queue_repo = QueueRepository(tmp_db)
        uhash = url_hash("https://example.com/existing")
        queue_repo.insert(QueuedItem(
            url="https://example.com/existing",
            url_hash=uhash,
            status="completed",
        ))

        mock_items = [
            SourceItem(
                url="https://example.com/existing",
                title="Existing",
                source_type=SourceType.ARTICLE,
                saved_at=datetime.now(timezone.utc),
            ),
        ]

        mock_connector = MagicMock()
        mock_connector.connector_id = "raindrop"
        mock_connector.fetch_since.return_value = mock_items

        with (
            patch("app.automation.discovery.get_settings") as mock_settings,
            patch("app.automation.discovery.get_inbox_connector", return_value=mock_connector),
            patch("app.automation.discovery.Database") as MockDB,
        ):
            mock_settings.return_value.automation_discover_batch_limit = 25
            mock_settings.return_value.db_path = tmp_db._path
            MockDB.return_value = tmp_db

            result = await discover_new_items(connector_id="raindrop")

        assert result.items_discovered == 0
        assert result.items_skipped_duplicate == 1

    @pytest.mark.asyncio
    async def test_cursor_advances_after_staging(self, tmp_db, tmp_vault):
        """Verify the sync cursor is only advanced after items are durably staged."""
        from app.automation.discovery import discover_new_items
        from app.models.source import SourceItem, SourceType
        from app.storage.repositories import SyncCursorRepository

        saved_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        mock_items = [
            SourceItem(
                url="https://example.com/cursor-test",
                title="Cursor Test",
                source_type=SourceType.ARTICLE,
                saved_at=saved_at,
            ),
        ]

        mock_connector = MagicMock()
        mock_connector.connector_id = "raindrop"
        mock_connector.fetch_since.return_value = mock_items

        with (
            patch("app.automation.discovery.get_settings") as mock_settings,
            patch("app.automation.discovery.get_inbox_connector", return_value=mock_connector),
            patch("app.automation.discovery.Database") as MockDB,
        ):
            mock_settings.return_value.automation_discover_batch_limit = 25
            mock_settings.return_value.db_path = tmp_db._path
            MockDB.return_value = tmp_db

            result = await discover_new_items(connector_id="raindrop")

        assert result.items_discovered == 1

        # Verify cursor was advanced
        cursor_repo = SyncCursorRepository(tmp_db)
        cursor = cursor_repo.get("raindrop")
        assert cursor is not None
        assert cursor.last_sync_at >= saved_at


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------


class TestProcessing:
    @pytest.mark.asyncio
    async def test_process_safe_mode(self, tmp_db, tmp_vault):
        """Safe mode processes items without expensive LLM calls."""
        from app.automation.processing import process_pending_items
        from app.models.source import SourceContent, SourceItem, SourceType

        # Insert a discovered item
        queue_repo = QueueRepository(tmp_db)
        queue_repo.insert(QueuedItem(
            connector_id="raindrop",
            url="https://example.com/safe-test",
            url_hash="safe1",
            title="Safe Mode Test",
            status="discovered",
        ))

        mock_content = SourceContent(
            source=SourceItem(
                url="https://example.com/safe-test",
                title="Safe Mode Test",
                source_type=SourceType.ARTICLE,
            ),
            cleaned_text="This is a test article about safe mode processing.",
            extraction_quality="full",
            extraction_method="trafilatura",
            url_hash="safe1",
        )

        with (
            patch("app.automation.processing.get_settings") as mock_settings,
            patch("app.automation.processing.Database") as MockDB,
            patch("app.connectors.fetchers.fetch_content", new_callable=AsyncMock, return_value=mock_content),
            patch("app.vault.writer.VaultWriter") as MockWriter,
            patch("app.vault.index_updater.rebuild_indexes"),
        ):
            mock_settings.return_value.automation_process_limit = 10
            mock_settings.return_value.automation_deep_enrich_limit_per_run = 3
            mock_settings.return_value.automation_deep_enrich_limit_per_day = 20
            mock_settings.return_value.automation_retry_max_attempts = 5
            mock_settings.return_value.automation_retry_base_seconds = 60
            mock_settings.return_value.db_path = tmp_db._path
            mock_settings.return_value.vault_path = tmp_vault
            MockDB.return_value = tmp_db

            mock_writer_instance = MagicMock()
            mock_writer_instance.write_raw_capture.return_value = MagicMock(path="inbox/raw/articles/safe-test.md")
            mock_writer_instance.write_source_note.return_value = MagicMock(path="wiki/sources/articles/safe-test.md")
            MockWriter.return_value = mock_writer_instance

            results = await process_pending_items(mode="safe", limit=10)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].mode == "safe"

    @pytest.mark.asyncio
    async def test_partial_batch_failure(self, tmp_db, tmp_vault):
        """One failed item should not block the rest."""
        from app.automation.processing import process_pending_items
        from app.models.source import SourceContent, SourceItem, SourceType

        queue_repo = QueueRepository(tmp_db)
        queue_repo.insert(QueuedItem(
            url="https://example.com/fail",
            url_hash="fail1",
            status="discovered",
        ))
        queue_repo.insert(QueuedItem(
            url="https://example.com/ok",
            url_hash="ok1",
            status="discovered",
        ))

        mock_content = SourceContent(
            source=SourceItem(
                url="https://example.com/ok",
                title="OK Article",
                source_type=SourceType.ARTICLE,
            ),
            cleaned_text="This works fine.",
            extraction_quality="full",
            url_hash="ok1",
        )

        call_count = 0

        async def mock_fetch(item):
            nonlocal call_count
            call_count += 1
            if "fail" in item.url:
                raise ConnectionError("network error")
            return mock_content

        with (
            patch("app.automation.processing.get_settings") as mock_settings,
            patch("app.automation.processing.Database") as MockDB,
            patch("app.connectors.fetchers.fetch_content", side_effect=mock_fetch),
            patch("app.vault.writer.VaultWriter") as MockWriter,
            patch("app.vault.index_updater.rebuild_indexes"),
        ):
            mock_settings.return_value.automation_process_limit = 10
            mock_settings.return_value.automation_deep_enrich_limit_per_run = 3
            mock_settings.return_value.automation_deep_enrich_limit_per_day = 20
            mock_settings.return_value.automation_retry_max_attempts = 5
            mock_settings.return_value.automation_retry_base_seconds = 60
            mock_settings.return_value.db_path = tmp_db._path
            mock_settings.return_value.vault_path = tmp_vault
            MockDB.return_value = tmp_db

            mock_writer_instance = MagicMock()
            mock_writer_instance.write_raw_capture.return_value = MagicMock(path="raw.md")
            mock_writer_instance.write_source_note.return_value = MagicMock(path="source.md")
            MockWriter.return_value = mock_writer_instance

            results = await process_pending_items(mode="safe", limit=10)

        assert len(results) == 2
        failed = [r for r in results if not r.success]
        succeeded = [r for r in results if r.success]
        assert len(failed) == 1
        assert len(succeeded) == 1

    @pytest.mark.asyncio
    async def test_retryable_failure_stays_retryable(self, tmp_db, tmp_vault):
        """Network errors should be marked retryable."""
        from app.automation.processing import process_pending_items

        queue_repo = QueueRepository(tmp_db)
        queue_repo.insert(QueuedItem(
            url="https://example.com/retry-me",
            url_hash="retry1",
            status="discovered",
        ))

        async def mock_fetch(item):
            raise ConnectionError("connection refused")

        with (
            patch("app.automation.processing.get_settings") as mock_settings,
            patch("app.automation.processing.Database") as MockDB,
            patch("app.connectors.fetchers.fetch_content", side_effect=mock_fetch),
        ):
            mock_settings.return_value.automation_process_limit = 10
            mock_settings.return_value.automation_deep_enrich_limit_per_run = 3
            mock_settings.return_value.automation_deep_enrich_limit_per_day = 20
            mock_settings.return_value.automation_retry_max_attempts = 5
            mock_settings.return_value.automation_retry_base_seconds = 60
            mock_settings.return_value.db_path = tmp_db._path
            MockDB.return_value = tmp_db

            results = await process_pending_items(mode="safe", limit=10)

        assert len(results) == 1
        assert results[0].success is False
        assert results[0].error_type == "network"

        # Check the item was marked retryable
        item = queue_repo.find_by_url_hash("retry1")
        assert item.status == QueueItemStatus.RETRYABLE_FAILED
        assert item.next_attempt_at is not None

    @pytest.mark.asyncio
    async def test_permanent_failure_after_max_attempts(self, tmp_db, tmp_vault):
        """Items exceeding max attempts should be permanently failed."""
        from app.automation.processing import process_pending_items

        queue_repo = QueueRepository(tmp_db)
        queue_repo.insert(QueuedItem(
            url="https://example.com/perm-fail",
            url_hash="perm1",
            status="discovered",
            attempt_count=4,  # Already at attempt 4, max is 5
        ))

        async def mock_fetch(item):
            raise ConnectionError("still failing")

        with (
            patch("app.automation.processing.get_settings") as mock_settings,
            patch("app.automation.processing.Database") as MockDB,
            patch("app.connectors.fetchers.fetch_content", side_effect=mock_fetch),
        ):
            mock_settings.return_value.automation_process_limit = 10
            mock_settings.return_value.automation_deep_enrich_limit_per_run = 3
            mock_settings.return_value.automation_deep_enrich_limit_per_day = 20
            mock_settings.return_value.automation_retry_max_attempts = 5
            mock_settings.return_value.automation_retry_base_seconds = 60
            mock_settings.return_value.db_path = tmp_db._path
            MockDB.return_value = tmp_db

            results = await process_pending_items(mode="safe", limit=10)

        item = queue_repo.find_by_url_hash("perm1")
        assert item.status == QueueItemStatus.PERMANENT_FAILED


# ---------------------------------------------------------------------------
# Automation Runner (one-shot)
# ---------------------------------------------------------------------------


class TestAutomationRunner:
    @pytest.mark.asyncio
    async def test_run_automation_discover_and_process(self):
        """run-pending performs discover + process + maintenance."""
        from app.automation.runner import run_automation

        with (
            patch("app.automation.runner.run_discover", new_callable=AsyncMock) as mock_discover,
            patch("app.automation.runner.run_process_pending", new_callable=AsyncMock) as mock_process,
            patch("app.automation.runner.run_maintenance", new_callable=AsyncMock) as mock_maintain,
            patch("app.automation.runner.get_settings") as mock_settings,
            patch("app.automation.runner.Database") as MockDB,
        ):
            mock_settings.return_value.automation_default_mode = "safe"
            mock_settings.return_value.db_path = Path("/tmp/test.db")

            mock_db = MagicMock()
            MockDB.return_value = mock_db

            mock_discover.return_value = {"items_discovered": 3, "items_skipped_duplicate": 1}
            mock_process.return_value = {"status": "ok", "succeeded": 2, "failed": 0}
            mock_maintain.return_value = {"status": "ok"}

            result = await run_automation(mode="safe", connector_id="raindrop")

        assert result["discover"]["items_discovered"] == 3
        assert result["process"]["succeeded"] == 2
        mock_discover.assert_called_once()
        mock_process.assert_called_once()
        mock_maintain.assert_called_once()

    @pytest.mark.asyncio
    async def test_idempotent_across_repeated_runs(self):
        """Running automation twice should not reprocess completed items."""
        from app.automation.runner import run_automation

        call_count = {"discover": 0, "process": 0}

        async def mock_discover(**kwargs):
            call_count["discover"] += 1
            return {"items_discovered": 0, "items_skipped_duplicate": 0}

        async def mock_process(**kwargs):
            call_count["process"] += 1
            return {"status": "ok", "succeeded": 0, "failed": 0}

        with (
            patch("app.automation.runner.run_discover", side_effect=mock_discover),
            patch("app.automation.runner.run_process_pending", side_effect=mock_process),
            patch("app.automation.runner.run_maintenance", new_callable=AsyncMock, return_value={"status": "ok"}),
            patch("app.automation.runner.get_settings") as mock_settings,
            patch("app.automation.runner.Database") as MockDB,
        ):
            mock_settings.return_value.automation_default_mode = "safe"
            mock_settings.return_value.db_path = Path("/tmp/test.db")
            MockDB.return_value = MagicMock()

            await run_automation(mode="safe")
            await run_automation(mode="safe")

        assert call_count["discover"] == 2  # Called each time
        assert call_count["process"] == 2  # Called each time (but no items processed)


# ---------------------------------------------------------------------------
# Queue persistence across runs
# ---------------------------------------------------------------------------


class TestQueuePersistence:
    def test_queue_state_persists(self, tmp_db):
        """Queue state persists across repository instantiations."""
        repo1 = QueueRepository(tmp_db)
        repo1.insert(QueuedItem(url="https://persist.com", url_hash="p1"))

        # New repo instance on same db
        repo2 = QueueRepository(tmp_db)
        found = repo2.find_by_url_hash("p1")
        assert found is not None
        assert found.url == "https://persist.com"

    def test_processed_items_not_reprocessed(self, tmp_db):
        """Completed items should not appear in pending."""
        repo = QueueRepository(tmp_db)
        item_id = repo.insert(QueuedItem(url="https://done.com", url_hash="done1"))
        repo.update_status(item_id, QueueItemStatus.COMPLETED)

        pending = repo.get_pending(limit=10)
        assert len(pending) == 0


# ---------------------------------------------------------------------------
# Mode behavior
# ---------------------------------------------------------------------------


class TestModes:
    def test_safe_mode_model(self):
        """Verify AutomationMode enum values."""
        assert AutomationMode.SAFE == "safe"
        assert AutomationMode.BALANCED == "balanced"
        assert AutomationMode.DEEP == "deep"

    def test_queue_item_statuses(self):
        """Verify QueueItemStatus enum values."""
        assert QueueItemStatus.DISCOVERED == "discovered"
        assert QueueItemStatus.PROCESSING == "processing"
        assert QueueItemStatus.COMPLETED == "completed"
        assert QueueItemStatus.RETRYABLE_FAILED == "retryable_failed"
        assert QueueItemStatus.PERMANENT_FAILED == "permanent_failed"
        assert QueueItemStatus.SKIPPED_DUPLICATE == "skipped_duplicate"


# ---------------------------------------------------------------------------
# Scheduler helpers
# ---------------------------------------------------------------------------


class TestSchedulerHelpers:
    def test_generate_launchd_plist(self):
        from app.automation.scheduler_helpers import generate_launchd_plist

        plist = generate_launchd_plist(mode="safe", interval_minutes=30)
        assert "com.epistora.automation" in plist
        assert "safe" in plist
        assert "<integer>1800</integer>" in plist

    def test_generate_systemd_timer(self):
        from app.automation.scheduler_helpers import generate_systemd_timer

        service, timer = generate_systemd_timer(mode="balanced", interval_minutes=60)
        assert "balanced" in service
        assert "60min" in timer

    def test_generate_windows_task(self):
        from app.automation.scheduler_helpers import generate_windows_task_xml

        xml = generate_windows_task_xml(mode="deep", interval_minutes=15)
        assert "deep" in xml
        assert "PT15M" in xml

    def test_generate_instructions(self):
        from app.automation.scheduler_helpers import generate_scheduler_instructions

        instructions = generate_scheduler_instructions(mode="safe", interval_minutes=30)
        assert "macOS" in instructions
        assert "Linux" in instructions
        assert "Windows" in instructions
        assert "safe" in instructions
