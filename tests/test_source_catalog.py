from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.db import CatalogSource, SourceProviderRef
from app.storage.repositories import SourceCatalogRepository


def test_metadata_only_source_upsert_dedupes_by_normalized_url(tmp_db):
    repo = SourceCatalogRepository(tmp_db)
    saved_at = datetime(2026, 5, 1, tzinfo=timezone.utc)

    first = repo.upsert_source(
        CatalogSource(
            url="https://example.com/article?utm_source=raindrop",
            title="Original Title",
            source_type="article",
            saved_at=saved_at,
        )
    )
    second = repo.upsert_source(
        CatalogSource(
            url="https://example.com/article",
            title="Updated Title",
            source_type="article",
            saved_at=saved_at,
        )
    )

    assert first.uid.startswith("src_")
    assert second.uid == first.uid
    assert second.metadata_status == "metadata_only"
    assert second.content_status == "not_fetched"
    assert second.title == "Updated Title"
    assert len(repo.list_sources(metadata_only=True)) == 1


def test_provider_ref_dedupe_updates_existing_ref(tmp_db):
    repo = SourceCatalogRepository(tmp_db)
    source = repo.upsert_source(
        CatalogSource(url="https://example.com/provider", title="Provider Test")
    )

    first = repo.attach_provider_ref(
        SourceProviderRef(
            source_uid=source.uid,
            provider="raindrop",
            external_id="123",
            external_url=source.url,
            title="First",
            metadata={"collection_id": 1},
        )
    )
    second = repo.attach_provider_ref(
        SourceProviderRef(
            source_uid=source.uid,
            provider="raindrop",
            external_id="123",
            external_url=source.url,
            title="Second",
            metadata={"collection_id": 2},
        )
    )

    assert second.id == first.id
    assert second.title == "Second"
    assert second.metadata == {"collection_id": 2}
    assert len(repo.provider_refs_for_source(source.uid)) == 1


def test_source_tag_normalization_and_snapshot(tmp_db):
    repo = SourceCatalogRepository(tmp_db)
    source = repo.upsert_source(CatalogSource(url="https://example.com/tags"))

    tags = repo.sync_tags(
        source.uid,
        [" AI ", "ai", "#Read Later", "read   later", ""],
        origin="provider",
    )
    refreshed = repo.get_source(source.uid)

    assert [tag.normalized_tag for tag in tags] == ["ai", "read later"]
    assert refreshed is not None
    assert refreshed.tag_snapshot == ["ai", "read later"]


def test_enqueue_processing_job_is_tied_to_source_uid(tmp_db):
    repo = SourceCatalogRepository(tmp_db)
    source = repo.upsert_source(
        CatalogSource(
            url="https://www.youtube.com/watch?v=abc123",
            title="Video",
            source_type="youtube",
        )
    )

    job = repo.enqueue_processing_job(
        source_uid=source.uid,
        task_type="capture",
        mode="safe",
        requested_by="user",
        requested_reason="manual source action",
    )
    duplicate = repo.enqueue_processing_job(
        source_uid=source.uid,
        task_type="capture",
        mode="safe",
        requested_by="user",
    )

    assert job.source_uid == source.uid
    assert job.job_uid.startswith("job_")
    assert job.status == "queued"
    assert job.priority_score > 0
    assert job.priority_reasons["explicit_request"] == 50
    assert duplicate.job_uid == job.job_uid


@pytest.mark.asyncio
async def test_discovery_creates_catalog_rows_without_fetching_or_vault_writes(
    tmp_db,
    tmp_vault,
):
    from app.automation.discovery import discover_new_items
    from app.automation.queue_store import QueueRepository
    from app.models.source import SourceItem, SourceType

    saved_at = datetime(2026, 5, 2, tzinfo=timezone.utc)
    mock_items = [
        SourceItem(
            url="https://example.com/new?utm_campaign=test",
            title="Catalog Only",
            source_type=SourceType.ARTICLE,
            tags=["AI", "Read Later"],
            external_id="rd-1",
            inbox_provider="raindrop",
            saved_at=saved_at,
            provider_metadata={"collection_id": 10},
            extra={"excerpt": "A metadata-only summary", "domain": "example.com"},
        )
    ]
    mock_connector = MagicMock()
    mock_connector.connector_id = "raindrop"
    mock_connector.fetch_since.return_value = mock_items

    with (
        patch("app.automation.discovery.get_settings") as mock_settings,
        patch("app.automation.discovery.get_inbox_connector", return_value=mock_connector),
        patch("app.automation.discovery.Database") as MockDB,
        patch("app.connectors.fetchers.fetch_content", new_callable=AsyncMock) as mock_fetch,
        patch("app.sinks.registry.build_default_sink") as mock_sink_builder,
    ):
        mock_settings.return_value.automation_discover_batch_limit = 25
        mock_settings.return_value.db_path = tmp_db._path
        mock_settings.return_value.vault_path = tmp_vault
        MockDB.return_value = tmp_db

        result = await discover_new_items(connector_id="raindrop")

    catalog_repo = SourceCatalogRepository(tmp_db)
    catalog_rows = catalog_repo.list_sources(metadata_only=True)
    queued = QueueRepository(tmp_db).list_items(limit=10)
    processed_count = tmp_db.conn.execute(
        "SELECT COUNT(*) AS c FROM processed_sources"
    ).fetchone()["c"]
    vault_note_count = tmp_db.conn.execute(
        "SELECT COUNT(*) AS c FROM vault_notes"
    ).fetchone()["c"]

    assert result.items_discovered == 1
    assert len(catalog_rows) == 1
    assert catalog_rows[0].title == "Catalog Only"
    assert catalog_rows[0].description == "A metadata-only summary"
    assert catalog_rows[0].tag_snapshot == ["ai", "read later"]
    assert len(catalog_repo.provider_refs_for_source(catalog_rows[0].uid)) == 1
    assert len(queued) == 1
    assert processed_count == 0
    assert vault_note_count == 0
    mock_fetch.assert_not_called()
    mock_sink_builder.assert_not_called()
