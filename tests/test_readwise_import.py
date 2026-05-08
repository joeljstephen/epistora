from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.backends.models import BackendResponse, BackendType
from app.models.db import SyncCursor
from app.models.source import (
    ExtractionQuality,
    PreExtractedSourceContent,
    ProviderContentMode,
    SourceItem,
    SourceType,
)
from app.storage.repositories import SourceCatalogRepository, SyncCursorRepository


def test_readwise_connector_maps_reader_documents_to_extracted_sources(respx_mock):
    from app.connectors.readwise import READWISE_READER_API_BASE, ReadwiseConnector

    respx_mock.get(f"{READWISE_READER_API_BASE}/list/").respond(
        json={
            "count": 1,
            "nextPageCursor": None,
            "results": [
                {
                    "id": "doc_123",
                    "url": "https://readwise.io/read/doc_123",
                    "source_url": "https://example.com/article",
                    "title": "Reader Article",
                    "author": "Jane Doe",
                    "category": "article",
                    "tags": {"ai": {"name": "AI"}, "read-later": {"name": "Read Later"}},
                    "saved_at": "2026-05-02T12:00:00+00:00",
                    "published_date": "2026-05-01",
                    "word_count": 500,
                    "html_content": "<article><p>Full article HTML</p></article>",
                    "summary": "Provider summary",
                }
            ],
        }
    )

    items = ReadwiseConnector(api_token="token").fetch_since(
        datetime(2026, 5, 1, tzinfo=timezone.utc),
        limit=10,
    )

    assert len(items) == 1
    assert items[0].url == "https://example.com/article"
    assert items[0].source_type == SourceType.ARTICLE
    assert items[0].tags == ["AI", "Read Later"]
    assert items[0].inbox_provider == "readwise"
    assert items[0].external_id == "doc_123"
    assert items[0].provider_content_mode == ProviderContentMode.EXTRACTED_CONTENT
    assert items[0].pre_extracted_content is not None
    assert "<article>" in items[0].pre_extracted_content.archived_markdown
    assert items[0].pre_extracted_content.author == "Jane Doe"


def test_readwise_connector_classifies_youtube_rss_items_by_url(respx_mock):
    from app.connectors.readwise import READWISE_READER_API_BASE, ReadwiseConnector

    respx_mock.get(f"{READWISE_READER_API_BASE}/list/").respond(
        json={
            "count": 1,
            "nextPageCursor": None,
            "results": [
                {
                    "id": "doc_video",
                    "url": "https://readwise.io/read/doc_video",
                    "source_url": "https://www.youtube.com/shorts/lA69cAMrOOE",
                    "title": "Building MCP under 60 seconds",
                    "category": "rss",
                    "site_name": "YouTube",
                    "html_content": "Transcript text from Readwise.",
                }
            ],
        }
    )

    items = ReadwiseConnector(api_token="token").fetch_since(
        datetime(2026, 5, 1, tzinfo=timezone.utc),
        limit=1,
    )

    assert items[0].source_type == SourceType.YOUTUBE
    assert items[0].pre_extracted_content is not None
    assert items[0].pre_extracted_content.raw_capture_kind == "readwise_video"


def test_readwise_connector_registers_when_token_is_configured():
    from app.config import Settings
    from app.connectors.registry import build_inbox_connectors

    settings = Settings(readwise_api_token="rw-token", raindrop_api_token="")

    connectors = build_inbox_connectors(settings)

    assert "readwise" in connectors


@pytest.mark.asyncio
async def test_readwise_import_writes_raw_capture_and_leaves_brief_pending(
    tmp_db,
    tmp_vault,
):
    from app.services.readwise_import_service import import_readwise_sources

    saved_at = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
    item = SourceItem(
        url="https://example.com/readwise-article?utm_source=readwise",
        title="Readwise Article",
        source_type=SourceType.ARTICLE,
        tags=["AI", "Read Later"],
        saved_at=saved_at,
        inbox_provider="readwise",
        external_id="rw_123",
        provider_content_mode=ProviderContentMode.EXTRACTED_CONTENT,
        provider_metadata={"category": "article"},
        pre_extracted_content=PreExtractedSourceContent(
            raw_text="Original article body from Readwise.",
            cleaned_text="Clean article body from Readwise.",
            archived_markdown="# Readwise Article\n\nClean article body from Readwise.",
            raw_capture_kind="readwise_article",
            extraction_quality=ExtractionQuality.MOSTLY_FULL,
            extraction_method="readwise",
            word_count=6,
            raw_metadata={"readwise_id": "rw_123"},
            evidence_metadata={"highlights": [{"text": "Clean article body"}]},
        ),
    )
    connector = MagicMock()
    connector.connector_id = "readwise"
    connector.fetch_since.return_value = [item]

    with (
        patch("app.services.readwise_import_service.get_settings") as mock_settings,
        patch(
            "app.services.readwise_import_service.get_inbox_connector",
            return_value=connector,
        ),
        patch("app.services.readwise_import_service.Database") as MockDB,
        patch("app.compiler.llm.run_structured", new_callable=AsyncMock) as mock_llm,
    ):
        mock_settings.return_value.db_path = tmp_db._path
        mock_settings.return_value.vault_path = tmp_vault
        mock_settings.return_value.evidence_blob_dir = ".system/blobs"
        mock_settings.return_value.evidence_blob_threshold_bytes = 50_000
        mock_settings.return_value.evidence_blob_preview_chars = 4_000
        MockDB.return_value = tmp_db

        result = await import_readwise_sources(limit=10)

    catalog_repo = SourceCatalogRepository(tmp_db)
    sources = catalog_repo.list_sources(provider="readwise", display_state="content_available")
    cursor = SyncCursorRepository(tmp_db).get("readwise")
    raw_capture = tmp_vault / "raw" / "articles" / "readwise-article.md"

    assert result.imported_count == 1
    assert result.failed_count == 0
    assert len(sources) == 1
    assert sources[0].title == "Readwise Article"
    assert sources[0].content_status == "available"
    assert sources[0].brief_status == "not_started"
    assert sources[0].metadata_status == "captured"
    assert sources[0].tag_snapshot == ["ai", "read later"]
    assert len(catalog_repo.provider_refs_for_source(sources[0].uid)) == 1
    assert cursor is not None
    assert raw_capture.exists()
    assert "Clean article body from Readwise." in raw_capture.read_text(encoding="utf-8")
    mock_llm.assert_not_called()


@pytest.mark.asyncio
async def test_readwise_import_isolates_item_failures(tmp_db, tmp_vault):
    from app.services.readwise_import_service import import_readwise_sources

    bad = SourceItem(
        url="https://example.com/missing-content",
        title="Missing Content",
        source_type=SourceType.ARTICLE,
        inbox_provider="readwise",
        external_id="rw_bad",
        provider_content_mode=ProviderContentMode.EXTRACTED_CONTENT,
    )
    good = SourceItem(
        url="https://example.com/good-content",
        title="Good Content",
        source_type=SourceType.ARTICLE,
        inbox_provider="readwise",
        external_id="rw_good",
        provider_content_mode=ProviderContentMode.EXTRACTED_CONTENT,
        pre_extracted_content=PreExtractedSourceContent(
            cleaned_text="Good captured content",
            raw_capture_kind="readwise_article",
            extraction_method="readwise",
        ),
    )
    connector = MagicMock()
    connector.connector_id = "readwise"
    connector.fetch_since.return_value = [bad, good]

    with (
        patch("app.services.readwise_import_service.get_settings") as mock_settings,
        patch(
            "app.services.readwise_import_service.get_inbox_connector",
            return_value=connector,
        ),
        patch("app.services.readwise_import_service.Database") as MockDB,
    ):
        mock_settings.return_value.db_path = tmp_db._path
        mock_settings.return_value.vault_path = tmp_vault
        mock_settings.return_value.evidence_blob_dir = ".system/blobs"
        mock_settings.return_value.evidence_blob_threshold_bytes = 50_000
        mock_settings.return_value.evidence_blob_preview_chars = 4_000
        MockDB.return_value = tmp_db

        result = await import_readwise_sources(limit=10)

    catalog_repo = SourceCatalogRepository(tmp_db)
    sources = catalog_repo.list_sources(provider="readwise", display_state="content_available")
    failed_sources = catalog_repo.list_sources(display_state="failed")
    cursor = SyncCursorRepository(tmp_db).get("readwise")

    assert result.imported_count == 1
    assert result.failed_count == 1
    assert "missing-content" in result.failures[0]
    assert len(sources) == 1
    assert sources[0].title == "Good Content"
    assert len(failed_sources) == 1
    assert failed_sources[0].title == "Missing Content"
    assert failed_sources[0].content_status == "failed"
    assert "pre-extracted content" in failed_sources[0].last_failure_reason
    assert cursor is not None


@pytest.mark.asyncio
async def test_force_readwise_import_ignores_existing_sync_cursor(tmp_db, tmp_vault):
    from app.services.readwise_import_service import import_readwise_sources

    SyncCursorRepository(tmp_db).upsert(
        SyncCursor(
            connector="readwise",
            last_sync_at=datetime(2026, 5, 8, tzinfo=timezone.utc),
        )
    )
    item = SourceItem(
        url="https://example.com/force-readwise",
        title="Force Readwise",
        source_type=SourceType.ARTICLE,
        inbox_provider="readwise",
        external_id="rw_force",
        provider_content_mode=ProviderContentMode.EXTRACTED_CONTENT,
        pre_extracted_content=PreExtractedSourceContent(
            cleaned_text="Force import captured content",
            raw_capture_kind="readwise_article",
            extraction_method="readwise",
        ),
    )
    connector = MagicMock()
    connector.connector_id = "readwise"
    connector.fetch_since.return_value = [item]

    with (
        patch("app.services.readwise_import_service.get_settings") as mock_settings,
        patch(
            "app.services.readwise_import_service.get_inbox_connector",
            return_value=connector,
        ),
        patch("app.services.readwise_import_service.Database") as MockDB,
    ):
        mock_settings.return_value.db_path = tmp_db._path
        mock_settings.return_value.vault_path = tmp_vault
        mock_settings.return_value.evidence_blob_dir = ".system/blobs"
        mock_settings.return_value.evidence_blob_threshold_bytes = 50_000
        mock_settings.return_value.evidence_blob_preview_chars = 4_000
        MockDB.return_value = tmp_db

        result = await import_readwise_sources(limit=1, force=True)

    since = connector.fetch_since.call_args.args[0]

    assert result.imported_count == 1
    assert since == datetime(2020, 1, 1, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_readwise_import_auto_briefs_only_configured_limit(tmp_db, tmp_vault):
    from app.services.readwise_import_service import import_readwise_sources

    items = [
        SourceItem(
            url=f"https://example.com/auto-brief-{index}",
            title=f"Auto Brief {index}",
            source_type=SourceType.ARTICLE,
            inbox_provider="readwise",
            external_id=f"rw_auto_{index}",
            provider_content_mode=ProviderContentMode.EXTRACTED_CONTENT,
            pre_extracted_content=PreExtractedSourceContent(
                cleaned_text=f"Captured evidence for item {index}.",
                raw_capture_kind="readwise_article",
                extraction_method="readwise",
            ),
        )
        for index in range(3)
    ]
    connector = MagicMock()
    connector.connector_id = "readwise"
    connector.fetch_since.return_value = items

    brief_payload = {
        "quick_brief": "Auto-briefed source.",
        "best_next_action": "Use the brief first.",
        "consume_recommendation": "Brief sufficient.",
        "key_ideas": ["Auto-briefing should be bounded."],
        "takeaways": ["Compile only the requested number of briefs."],
        "important_terms": ["Auto brief"],
        "topics": ["Readwise"],
        "entities": [],
        "concepts": [],
        "read_verdict": "brief_sufficient",
        "why_read_or_skip": "The brief is enough for now.",
        "key_sections": ["Main point"],
    }

    with (
        patch("app.services.readwise_import_service.get_settings") as mock_settings,
        patch(
            "app.services.readwise_import_service.get_inbox_connector",
            return_value=connector,
        ),
        patch("app.services.readwise_import_service.Database") as MockDB,
        patch("app.services.brief_service.get_settings") as brief_settings,
        patch("app.services.brief_service.Database") as BriefDB,
        patch(
            "app.services.brief_service.run_structured",
            new_callable=AsyncMock,
            return_value=BackendResponse(
                text=json.dumps(brief_payload),
                success=True,
                backend_used=BackendType.API,
                model_used="test-model",
            ),
        ) as mock_llm,
    ):
        mock_settings.return_value.db_path = tmp_db._path
        mock_settings.return_value.vault_path = tmp_vault
        mock_settings.return_value.evidence_blob_dir = ".system/blobs"
        mock_settings.return_value.evidence_blob_threshold_bytes = 50_000
        mock_settings.return_value.evidence_blob_preview_chars = 4_000
        brief_settings.return_value = mock_settings.return_value
        MockDB.return_value = tmp_db
        BriefDB.return_value = tmp_db

        result = await import_readwise_sources(limit=3, auto_brief_limit=2)

    catalog_repo = SourceCatalogRepository(tmp_db)
    ready = catalog_repo.list_sources(display_state="brief_ready")
    pending = catalog_repo.list_sources(display_state="content_available")

    assert result.imported_count == 3
    assert result.auto_brief_result is not None
    assert result.auto_brief_result.compiled_count == 2
    assert len(ready) == 2
    assert len(pending) == 1
    assert mock_llm.await_count == 2


@pytest.mark.asyncio
async def test_readwise_import_auto_brief_default_limit_is_five(tmp_db, tmp_vault):
    from app.services.readwise_import_service import import_readwise_sources

    items = [
        SourceItem(
            url=f"https://example.com/default-auto-brief-{index}",
            title=f"Default Auto Brief {index}",
            source_type=SourceType.ARTICLE,
            inbox_provider="readwise",
            external_id=f"rw_default_auto_{index}",
            provider_content_mode=ProviderContentMode.EXTRACTED_CONTENT,
            pre_extracted_content=PreExtractedSourceContent(
                cleaned_text=f"Captured evidence for default item {index}.",
                raw_capture_kind="readwise_article",
                extraction_method="readwise",
            ),
        )
        for index in range(6)
    ]
    connector = MagicMock()
    connector.connector_id = "readwise"
    connector.fetch_since.return_value = items

    brief_payload = {
        "quick_brief": "Default auto-briefed source.",
        "best_next_action": "Use the brief first.",
        "consume_recommendation": "Brief sufficient.",
        "key_ideas": ["Default auto-briefing should be bounded."],
        "takeaways": ["Compile five by default."],
        "important_terms": ["Auto brief"],
        "topics": ["Readwise"],
        "entities": [],
        "concepts": [],
        "read_verdict": "brief_sufficient",
        "why_read_or_skip": "The brief is enough for now.",
        "key_sections": ["Main point"],
    }

    with (
        patch("app.services.readwise_import_service.get_settings") as mock_settings,
        patch(
            "app.services.readwise_import_service.get_inbox_connector",
            return_value=connector,
        ),
        patch("app.services.readwise_import_service.Database") as MockDB,
        patch("app.services.brief_service.get_settings") as brief_settings,
        patch("app.services.brief_service.Database") as BriefDB,
        patch(
            "app.services.brief_service.run_structured",
            new_callable=AsyncMock,
            return_value=BackendResponse(
                text=json.dumps(brief_payload),
                success=True,
                backend_used=BackendType.API,
                model_used="test-model",
            ),
        ) as mock_llm,
    ):
        mock_settings.return_value.db_path = tmp_db._path
        mock_settings.return_value.vault_path = tmp_vault
        mock_settings.return_value.evidence_blob_dir = ".system/blobs"
        mock_settings.return_value.evidence_blob_threshold_bytes = 50_000
        mock_settings.return_value.evidence_blob_preview_chars = 4_000
        brief_settings.return_value = mock_settings.return_value
        MockDB.return_value = tmp_db
        BriefDB.return_value = tmp_db

        result = await import_readwise_sources(limit=6, auto_brief=True)

    catalog_repo = SourceCatalogRepository(tmp_db)
    ready = catalog_repo.list_sources(display_state="brief_ready")
    pending = catalog_repo.list_sources(display_state="content_available")

    assert result.imported_count == 6
    assert result.auto_brief_result is not None
    assert result.auto_brief_result.compiled_count == 5
    assert len(ready) == 5
    assert len(pending) == 1
    assert mock_llm.await_count == 5


@pytest.mark.asyncio
async def test_readwise_import_reports_auto_brief_progress(tmp_db, tmp_vault):
    from app.services.readwise_import_service import import_readwise_sources

    item = SourceItem(
        url="https://example.com/progress-auto-brief",
        title="Progress Auto Brief",
        source_type=SourceType.ARTICLE,
        inbox_provider="readwise",
        external_id="rw_progress",
        provider_content_mode=ProviderContentMode.EXTRACTED_CONTENT,
        pre_extracted_content=PreExtractedSourceContent(
            cleaned_text="Captured evidence for progress.",
            raw_capture_kind="readwise_article",
            extraction_method="readwise",
        ),
    )
    connector = MagicMock()
    connector.connector_id = "readwise"
    connector.fetch_since.return_value = [item]
    brief_payload = {
        "quick_brief": "Progress source.",
        "best_next_action": "Use the brief first.",
        "consume_recommendation": "Brief sufficient.",
        "key_ideas": ["Progress should be visible."],
        "takeaways": ["Report auto-brief progress."],
        "important_terms": ["Progress"],
        "topics": ["Readwise"],
        "entities": [],
        "concepts": [],
        "read_verdict": "brief_sufficient",
        "why_read_or_skip": "The brief is enough for now.",
        "key_sections": ["Main point"],
    }
    events: list[tuple[str, dict]] = []

    with (
        patch("app.services.readwise_import_service.get_settings") as mock_settings,
        patch(
            "app.services.readwise_import_service.get_inbox_connector",
            return_value=connector,
        ),
        patch("app.services.readwise_import_service.Database") as MockDB,
        patch("app.services.brief_service.get_settings") as brief_settings,
        patch("app.services.brief_service.Database") as BriefDB,
        patch(
            "app.services.brief_service.run_structured",
            new_callable=AsyncMock,
            return_value=BackendResponse(
                text=json.dumps(brief_payload),
                success=True,
                backend_used=BackendType.API,
                model_used="test-model",
            ),
        ),
    ):
        mock_settings.return_value.db_path = tmp_db._path
        mock_settings.return_value.vault_path = tmp_vault
        mock_settings.return_value.evidence_blob_dir = ".system/blobs"
        mock_settings.return_value.evidence_blob_threshold_bytes = 50_000
        mock_settings.return_value.evidence_blob_preview_chars = 4_000
        brief_settings.return_value = mock_settings.return_value
        MockDB.return_value = tmp_db
        BriefDB.return_value = tmp_db

        await import_readwise_sources(
            limit=1,
            auto_brief=True,
            progress_callback=lambda stage, payload: events.append((stage, payload)),
        )

    stages = [stage for stage, _ in events]

    assert "readwise_import_done" in stages
    assert "readwise_auto_brief_start" in stages
    assert "readwise_auto_brief_done" in stages
