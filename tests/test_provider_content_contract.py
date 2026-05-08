from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.source import (
    ExtractionQuality,
    PreExtractedSourceContent,
    ProviderContentMode,
    SourceItem,
    SourceType,
)


def test_raindrop_connector_items_remain_link_only(respx_mock):
    from app.connectors.raindrop import RAINDROP_API_BASE, RaindropConnector

    respx_mock.get(f"{RAINDROP_API_BASE}/raindrops/0").respond(
        json={
            "items": [
                {
                    "_id": 123,
                    "link": "https://example.com/article",
                    "title": "Saved article",
                    "created": "2026-05-01T12:00:00Z",
                    "tags": ["reading"],
                    "collection": {"$id": 0},
                }
            ]
        }
    )

    items = RaindropConnector(api_token="token").fetch_recent(limit=1)

    assert len(items) == 1
    assert items[0].provider_content_mode == ProviderContentMode.LINK_ONLY
    assert items[0].pre_extracted_content is None


def test_link_only_sources_do_not_need_pre_extracted_content():
    item = SourceItem(
        url="https://example.com/article",
        title="Saved article",
        source_type=SourceType.ARTICLE,
        inbox_provider="raindrop",
    )

    assert item.provider_content_mode == ProviderContentMode.LINK_ONLY
    assert item.pre_extracted_content is None


def test_extracted_content_sources_can_carry_provider_evidence():
    item = SourceItem(
        url="https://example.com/article",
        title="Readwise article",
        source_type=SourceType.ARTICLE,
        inbox_provider="readwise",
        provider_content_mode=ProviderContentMode.EXTRACTED_CONTENT,
        pre_extracted_content=PreExtractedSourceContent(
            raw_text="Original Readwise article body",
            cleaned_text="Clean article body",
            archived_markdown="# Readwise article\n\nClean article body",
            raw_capture_kind="readwise_article",
            extraction_quality=ExtractionQuality.MOSTLY_FULL,
            extraction_method="readwise",
            word_count=4,
            raw_metadata={"readwise_id": "rw_123"},
            evidence_metadata={
                "highlights": [
                    {
                        "text": "Important passage",
                        "note": "Remember this",
                    }
                ]
            },
        ),
    )

    assert item.provider_content_mode == ProviderContentMode.EXTRACTED_CONTENT
    assert item.pre_extracted_content is not None
    assert item.pre_extracted_content.cleaned_text == "Clean article body"
    assert item.pre_extracted_content.evidence_metadata["highlights"][0]["text"] == (
        "Important passage"
    )


@pytest.mark.asyncio
async def test_raindrop_sync_uses_link_only_single_pass_ingest_path(tmp_db):
    from app.models.results import IngestResult
    from app.services.ingest_service import sync_inbox

    item = SourceItem(
        url="https://example.com/link-only",
        title="Link Only",
        source_type=SourceType.ARTICLE,
        inbox_provider="raindrop",
        external_id="rd_1",
    )
    connector = MagicMock()
    connector.connector_id = "raindrop"
    connector.fetch_since.return_value = [item]

    async def fake_ainvoke(state):
        synced_item = state["item"]
        assert synced_item.provider_content_mode == ProviderContentMode.LINK_ONLY
        assert synced_item.pre_extracted_content is None
        return {
            "result": IngestResult(
                source_url=synced_item.url,
                source_title=synced_item.title,
                source_type=synced_item.source_type.value,
            )
        }

    graph = MagicMock()
    graph.ainvoke = AsyncMock(side_effect=fake_ainvoke)

    with (
        patch("app.services.ingest_service.get_settings") as settings,
        patch("app.services.ingest_service.get_inbox_connector", return_value=connector),
        patch("app.services.ingest_service.get_ingest_graph", return_value=graph),
        patch("app.services.ingest_service.Database") as DB,
    ):
        settings.return_value.db_path = tmp_db._path
        DB.return_value = tmp_db

        results = await sync_inbox(connector_id="raindrop", limit=1)

    assert len(results) == 1
    assert results[0].source_url == "https://example.com/link-only"
    graph.ainvoke.assert_awaited_once()
