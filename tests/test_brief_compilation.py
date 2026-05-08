from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.backends.models import BackendResponse, BackendType
from app.models.source import (
    PreExtractedSourceContent,
    ProviderContentMode,
    SourceItem,
    SourceType,
)
from app.storage.repositories import SourceCatalogRepository


@pytest.mark.asyncio
async def test_pending_readwise_source_compiles_into_source_note(tmp_db, tmp_vault):
    from app.services.brief_service import compile_pending_source_briefs
    from app.services.readwise_import_service import import_readwise_sources

    item = SourceItem(
        url="https://example.com/brief-me",
        title="Brief Me",
        source_type=SourceType.ARTICLE,
        saved_at=datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc),
        inbox_provider="readwise",
        external_id="rw_brief",
        provider_content_mode=ProviderContentMode.EXTRACTED_CONTENT,
        pre_extracted_content=PreExtractedSourceContent(
            cleaned_text="This article explains brief-first reading for saved sources.",
            raw_capture_kind="readwise_article",
            extraction_method="readwise",
            word_count=9,
        ),
    )
    connector = MagicMock()
    connector.connector_id = "readwise"
    connector.fetch_since.return_value = [item]

    with (
        patch("app.services.readwise_import_service.get_settings") as import_settings,
        patch("app.services.readwise_import_service.get_inbox_connector", return_value=connector),
        patch("app.services.readwise_import_service.Database") as ImportDB,
    ):
        import_settings.return_value.db_path = tmp_db._path
        import_settings.return_value.vault_path = tmp_vault
        import_settings.return_value.evidence_blob_dir = ".system/blobs"
        import_settings.return_value.evidence_blob_threshold_bytes = 50_000
        import_settings.return_value.evidence_blob_preview_chars = 4_000
        ImportDB.return_value = tmp_db
        await import_readwise_sources(limit=1)

    analysis = {
        "quick_brief": "A practical case for deciding whether to read before reading.",
        "best_next_action": "Read the brief, then skip the original unless this is active.",
        "consume_recommendation": "Brief sufficient for now.",
        "key_ideas": ["Briefs should support triage decisions."],
        "takeaways": ["Use a Source Brief before opening the original."],
        "important_terms": ["Source Brief"],
        "topics": ["Knowledge management"],
        "entities": [{"name": "Readwise", "type": "tool", "description": "Reader app"}],
        "concepts": [{"name": "Brief-first reading", "definition": "Triage before reading"}],
        "read_verdict": "brief_sufficient",
        "why_read_or_skip": "The captured evidence is enough for the current decision.",
        "key_sections": ["The triage argument"],
    }

    with (
        patch("app.services.brief_service.get_settings") as brief_settings,
        patch("app.services.brief_service.Database") as BriefDB,
        patch(
            "app.services.brief_service.run_structured",
            new_callable=AsyncMock,
            return_value=BackendResponse(
                text=json.dumps(analysis),
                success=True,
                backend_used=BackendType.API,
                model_used="test-model",
            ),
        ) as mock_llm,
    ):
        brief_settings.return_value.db_path = tmp_db._path
        brief_settings.return_value.vault_path = tmp_vault
        brief_settings.return_value.evidence_blob_dir = ".system/blobs"
        brief_settings.return_value.evidence_blob_threshold_bytes = 50_000
        brief_settings.return_value.evidence_blob_preview_chars = 4_000
        BriefDB.return_value = tmp_db

        result = await compile_pending_source_briefs(limit=1)

    catalog_repo = SourceCatalogRepository(tmp_db)
    ready = catalog_repo.list_sources(display_state="brief_ready")
    source_note = tmp_vault / "wiki" / "sources" / "articles" / "brief-me.md"

    assert result.compiled_count == 1
    assert result.failed_count == 0
    assert len(ready) == 1
    assert ready[0].brief_status == "ready"
    assert source_note.exists()
    rendered = source_note.read_text(encoding="utf-8")
    assert "A practical case for deciding whether to read before reading." in rendered
    assert "Use a Source Brief before opening the original." in rendered
    mock_llm.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_brief_compilation_marks_source_failed_without_losing_raw_capture(
    tmp_db,
    tmp_vault,
):
    from app.services.brief_service import compile_pending_source_briefs
    from app.services.readwise_import_service import import_readwise_sources

    item = SourceItem(
        url="https://example.com/fail-brief",
        title="Fail Brief",
        source_type=SourceType.ARTICLE,
        inbox_provider="readwise",
        external_id="rw_fail",
        provider_content_mode=ProviderContentMode.EXTRACTED_CONTENT,
        pre_extracted_content=PreExtractedSourceContent(
            cleaned_text="Captured evidence remains available.",
            raw_capture_kind="readwise_article",
            extraction_method="readwise",
        ),
    )
    connector = MagicMock()
    connector.connector_id = "readwise"
    connector.fetch_since.return_value = [item]

    with (
        patch("app.services.readwise_import_service.get_settings") as import_settings,
        patch("app.services.readwise_import_service.get_inbox_connector", return_value=connector),
        patch("app.services.readwise_import_service.Database") as ImportDB,
    ):
        import_settings.return_value.db_path = tmp_db._path
        import_settings.return_value.vault_path = tmp_vault
        import_settings.return_value.evidence_blob_dir = ".system/blobs"
        import_settings.return_value.evidence_blob_threshold_bytes = 50_000
        import_settings.return_value.evidence_blob_preview_chars = 4_000
        ImportDB.return_value = tmp_db
        await import_readwise_sources(limit=1)

    with (
        patch("app.services.brief_service.get_settings") as brief_settings,
        patch("app.services.brief_service.Database") as BriefDB,
        patch(
            "app.services.brief_service.run_structured",
            new_callable=AsyncMock,
            return_value=BackendResponse(
                text="",
                success=False,
                error="backend unavailable",
                backend_used=BackendType.API,
            ),
        ),
    ):
        brief_settings.return_value.db_path = tmp_db._path
        brief_settings.return_value.vault_path = tmp_vault
        brief_settings.return_value.evidence_blob_dir = ".system/blobs"
        brief_settings.return_value.evidence_blob_threshold_bytes = 50_000
        brief_settings.return_value.evidence_blob_preview_chars = 4_000
        BriefDB.return_value = tmp_db

        result = await compile_pending_source_briefs(limit=1)

    failed = SourceCatalogRepository(tmp_db).list_sources(display_state="failed")
    raw_capture = tmp_vault / "raw" / "articles" / "fail-brief.md"
    source_note = tmp_vault / "wiki" / "sources" / "articles" / "fail-brief.md"

    assert result.compiled_count == 0
    assert result.failed_count == 1
    assert len(failed) == 1
    assert failed[0].brief_status == "failed"
    assert "backend unavailable" in failed[0].last_failure_reason
    assert raw_capture.exists()
    assert not source_note.exists()


@pytest.mark.asyncio
async def test_force_rebrief_regenerates_ready_source_note(tmp_db, tmp_vault):
    from app.services.brief_service import compile_pending_source_briefs
    from app.services.readwise_import_service import import_readwise_sources

    item = SourceItem(
        url="https://example.com/rebrief",
        title="Rebrief",
        source_type=SourceType.ARTICLE,
        inbox_provider="readwise",
        external_id="rw_rebrief",
        provider_content_mode=ProviderContentMode.EXTRACTED_CONTENT,
        pre_extracted_content=PreExtractedSourceContent(
            cleaned_text="Evidence for regeneration.",
            raw_capture_kind="readwise_article",
            extraction_method="readwise",
        ),
    )
    connector = MagicMock()
    connector.connector_id = "readwise"
    connector.fetch_since.return_value = [item]

    with (
        patch("app.services.readwise_import_service.get_settings") as import_settings,
        patch("app.services.readwise_import_service.get_inbox_connector", return_value=connector),
        patch("app.services.readwise_import_service.Database") as ImportDB,
    ):
        import_settings.return_value.db_path = tmp_db._path
        import_settings.return_value.vault_path = tmp_vault
        import_settings.return_value.evidence_blob_dir = ".system/blobs"
        import_settings.return_value.evidence_blob_threshold_bytes = 50_000
        import_settings.return_value.evidence_blob_preview_chars = 4_000
        ImportDB.return_value = tmp_db
        await import_readwise_sources(limit=1)

    responses = [
        BackendResponse(
            text=json.dumps(
                _article_brief_payload("First brief", "First takeaway")
            ),
            success=True,
            backend_used=BackendType.API,
            model_used="test-model",
        ),
        BackendResponse(
            text=json.dumps(
                _article_brief_payload("Regenerated brief", "Updated takeaway")
            ),
            success=True,
            backend_used=BackendType.API,
            model_used="test-model",
        ),
    ]

    with (
        patch("app.services.brief_service.get_settings") as brief_settings,
        patch("app.services.brief_service.Database") as BriefDB,
        patch(
            "app.services.brief_service.run_structured",
            new_callable=AsyncMock,
            side_effect=responses,
        ) as mock_llm,
    ):
        brief_settings.return_value.db_path = tmp_db._path
        brief_settings.return_value.vault_path = tmp_vault
        brief_settings.return_value.evidence_blob_dir = ".system/blobs"
        brief_settings.return_value.evidence_blob_threshold_bytes = 50_000
        brief_settings.return_value.evidence_blob_preview_chars = 4_000
        BriefDB.return_value = tmp_db

        first = await compile_pending_source_briefs(limit=1)
        second = await compile_pending_source_briefs(limit=1, force=True)

    source_note = tmp_vault / "wiki" / "sources" / "articles" / "rebrief.md"
    rendered = source_note.read_text(encoding="utf-8")

    assert first.compiled_count == 1
    assert second.compiled_count == 1
    assert mock_llm.await_count == 2
    assert "Regenerated brief" in rendered
    assert "Updated takeaway" in rendered


@pytest.mark.asyncio
async def test_source_brief_compiler_targets_requested_source(tmp_db, tmp_vault):
    from app.services.brief_service import compile_source_brief
    from app.services.readwise_import_service import import_readwise_sources

    items = [
        SourceItem(
            url="https://example.com/targeted",
            title="Targeted",
            source_type=SourceType.ARTICLE,
            inbox_provider="readwise",
            external_id="rw_targeted",
            provider_content_mode=ProviderContentMode.EXTRACTED_CONTENT,
            pre_extracted_content=PreExtractedSourceContent(
                cleaned_text="Evidence for the specifically selected source.",
                raw_capture_kind="readwise_article",
                extraction_method="readwise",
            ),
        ),
        SourceItem(
            url="https://example.com/untouched",
            title="Untouched",
            source_type=SourceType.ARTICLE,
            inbox_provider="readwise",
            external_id="rw_untouched",
            provider_content_mode=ProviderContentMode.EXTRACTED_CONTENT,
            pre_extracted_content=PreExtractedSourceContent(
                cleaned_text="Evidence that should stay pending.",
                raw_capture_kind="readwise_article",
                extraction_method="readwise",
            ),
        ),
    ]
    connector = MagicMock()
    connector.connector_id = "readwise"
    connector.fetch_since.return_value = items

    with (
        patch("app.services.readwise_import_service.get_settings") as import_settings,
        patch("app.services.readwise_import_service.get_inbox_connector", return_value=connector),
        patch("app.services.readwise_import_service.Database") as ImportDB,
    ):
        import_settings.return_value.db_path = tmp_db._path
        import_settings.return_value.vault_path = tmp_vault
        import_settings.return_value.evidence_blob_dir = ".system/blobs"
        import_settings.return_value.evidence_blob_threshold_bytes = 50_000
        import_settings.return_value.evidence_blob_preview_chars = 4_000
        ImportDB.return_value = tmp_db
        await import_readwise_sources(limit=2)

    target = SourceCatalogRepository(tmp_db).list_sources(query="targeted")[0]

    with (
        patch("app.services.brief_service.get_settings") as brief_settings,
        patch("app.services.brief_service.Database") as BriefDB,
        patch(
            "app.services.brief_service.run_structured",
            new_callable=AsyncMock,
            return_value=BackendResponse(
                text=json.dumps(
                    _article_brief_payload(
                        "Only the targeted source was briefed.",
                        "Leave unrelated pending sources alone.",
                    )
                ),
                success=True,
                backend_used=BackendType.API,
                model_used="test-model",
            ),
        ) as mock_llm,
    ):
        brief_settings.return_value.db_path = tmp_db._path
        brief_settings.return_value.vault_path = tmp_vault
        brief_settings.return_value.evidence_blob_dir = ".system/blobs"
        brief_settings.return_value.evidence_blob_threshold_bytes = 50_000
        brief_settings.return_value.evidence_blob_preview_chars = 4_000
        BriefDB.return_value = tmp_db

        result = await compile_source_brief(target.uid)

    ready_titles = {
        source.title
        for source in SourceCatalogRepository(tmp_db).list_sources(display_state="brief_ready")
    }
    pending_titles = {
        source.title
        for source in SourceCatalogRepository(tmp_db).list_sources(
            display_state="content_available"
        )
    }

    assert result.compiled_count == 1
    assert ready_titles == {"Targeted"}
    assert pending_titles == {"Untouched"}
    mock_llm.assert_awaited_once()


@pytest.mark.asyncio
async def test_youtube_source_brief_renders_watch_verdict(tmp_db, tmp_vault):
    from app.services.brief_service import compile_pending_source_briefs
    from app.services.readwise_import_service import import_readwise_sources

    item = SourceItem(
        url="https://www.youtube.com/watch?v=abc123",
        title="Watch Me",
        source_type=SourceType.YOUTUBE,
        inbox_provider="readwise",
        external_id="rw_video",
        provider_content_mode=ProviderContentMode.EXTRACTED_CONTENT,
        pre_extracted_content=PreExtractedSourceContent(
            cleaned_text="Transcript segment about useful parts and filler.",
            raw_capture_kind="readwise_video",
            extraction_method="readwise",
        ),
    )
    connector = MagicMock()
    connector.connector_id = "readwise"
    connector.fetch_since.return_value = [item]

    with (
        patch("app.services.readwise_import_service.get_settings") as import_settings,
        patch("app.services.readwise_import_service.get_inbox_connector", return_value=connector),
        patch("app.services.readwise_import_service.Database") as ImportDB,
    ):
        import_settings.return_value.db_path = tmp_db._path
        import_settings.return_value.vault_path = tmp_vault
        import_settings.return_value.evidence_blob_dir = ".system/blobs"
        import_settings.return_value.evidence_blob_threshold_bytes = 50_000
        import_settings.return_value.evidence_blob_preview_chars = 4_000
        ImportDB.return_value = tmp_db
        await import_readwise_sources(limit=1)

    video_payload = {
        "quick_brief": "A video with one useful segment.",
        "best_next_action": "Use the transcript and skip playback.",
        "consume_recommendation": "Transcript is enough.",
        "key_ideas": ["The useful segment is concise."],
        "takeaways": ["Do not watch the full video."],
        "important_terms": ["Signal vs filler"],
        "topics": ["Video triage"],
        "entities": [],
        "concepts": [],
        "watch_verdict": "transcript_sufficient",
        "watch_verdict_reasoning": "The transcript contains the high-signal material.",
        "quick_section_guide": "0:00 useful section",
        "detailed_sections": "The opening contains the relevant point.",
        "signal_vs_filler": "Mostly filler after the opening.",
    }

    with (
        patch("app.services.brief_service.get_settings") as brief_settings,
        patch("app.services.brief_service.Database") as BriefDB,
        patch(
            "app.services.brief_service.run_structured",
            new_callable=AsyncMock,
            return_value=BackendResponse(
                text=json.dumps(video_payload),
                success=True,
                backend_used=BackendType.API,
                model_used="test-model",
            ),
        ),
    ):
        brief_settings.return_value.db_path = tmp_db._path
        brief_settings.return_value.vault_path = tmp_vault
        brief_settings.return_value.evidence_blob_dir = ".system/blobs"
        brief_settings.return_value.evidence_blob_threshold_bytes = 50_000
        brief_settings.return_value.evidence_blob_preview_chars = 4_000
        BriefDB.return_value = tmp_db

        result = await compile_pending_source_briefs(limit=1)

    source_note = tmp_vault / "wiki" / "sources" / "videos" / "watch-me.md"
    rendered = source_note.read_text(encoding="utf-8")

    assert result.compiled_count == 1
    assert "transcript_sufficient" in rendered
    assert "The transcript contains the high-signal material." in rendered


@pytest.mark.asyncio
async def test_thread_source_brief_renders_thread_summary(tmp_db, tmp_vault):
    from app.services.brief_service import compile_pending_source_briefs
    from app.services.readwise_import_service import import_readwise_sources

    item = SourceItem(
        url="https://x.com/user/status/123",
        title="Thread Me",
        source_type=SourceType.X_THREAD,
        inbox_provider="readwise",
        external_id="rw_thread",
        provider_content_mode=ProviderContentMode.EXTRACTED_CONTENT,
        pre_extracted_content=PreExtractedSourceContent(
            cleaned_text="Thread text with several claims.",
            raw_capture_kind="readwise_thread",
            extraction_method="readwise",
        ),
    )
    connector = MagicMock()
    connector.connector_id = "readwise"
    connector.fetch_since.return_value = [item]

    with (
        patch("app.services.readwise_import_service.get_settings") as import_settings,
        patch("app.services.readwise_import_service.get_inbox_connector", return_value=connector),
        patch("app.services.readwise_import_service.Database") as ImportDB,
    ):
        import_settings.return_value.db_path = tmp_db._path
        import_settings.return_value.vault_path = tmp_vault
        import_settings.return_value.evidence_blob_dir = ".system/blobs"
        import_settings.return_value.evidence_blob_threshold_bytes = 50_000
        import_settings.return_value.evidence_blob_preview_chars = 4_000
        ImportDB.return_value = tmp_db
        await import_readwise_sources(limit=1)

    thread_payload = {
        "quick_brief": "A thread about brief compilation.",
        "best_next_action": "Use the claims as a quick reference.",
        "consume_recommendation": "Brief sufficient.",
        "key_ideas": ["Threads should be distilled into claims."],
        "takeaways": ["Extract claims before deciding to open the thread."],
        "important_terms": ["Thread summary"],
        "topics": ["Thread triage"],
        "entities": [],
        "concepts": [],
        "thread_summary": "The thread argues that concise claims are more useful than recaps.",
        "main_claims": ["Claims beat chronology for quick reuse."],
        "useful_links_or_references": ["https://example.com/reference"],
    }

    with (
        patch("app.services.brief_service.get_settings") as brief_settings,
        patch("app.services.brief_service.Database") as BriefDB,
        patch(
            "app.services.brief_service.run_structured",
            new_callable=AsyncMock,
            return_value=BackendResponse(
                text=json.dumps(thread_payload),
                success=True,
                backend_used=BackendType.API,
                model_used="test-model",
            ),
        ),
    ):
        brief_settings.return_value.db_path = tmp_db._path
        brief_settings.return_value.vault_path = tmp_vault
        brief_settings.return_value.evidence_blob_dir = ".system/blobs"
        brief_settings.return_value.evidence_blob_threshold_bytes = 50_000
        brief_settings.return_value.evidence_blob_preview_chars = 4_000
        BriefDB.return_value = tmp_db

        result = await compile_pending_source_briefs(limit=1)

    source_note = tmp_vault / "wiki" / "sources" / "threads" / "thread-me.md"
    rendered = source_note.read_text(encoding="utf-8")

    assert result.compiled_count == 1
    assert "The thread argues that concise claims are more useful than recaps." in rendered
    assert "Extract claims before deciding to open the thread." in rendered


@pytest.mark.asyncio
async def test_pending_briefs_are_selected_by_priority(tmp_db, tmp_vault):
    from app.services.brief_service import compile_pending_source_briefs
    from app.services.readwise_import_service import import_readwise_sources

    items = [
        SourceItem(
            url="https://example.com/plain-old",
            title="Plain Old",
            source_type=SourceType.ARTICLE,
            saved_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
            inbox_provider="readwise",
            external_id="plain",
            provider_content_mode=ProviderContentMode.EXTRACTED_CONTENT,
            pre_extracted_content=PreExtractedSourceContent(
                cleaned_text="Plain old evidence.",
                raw_capture_kind="readwise_article",
                extraction_method="readwise",
            ),
        ),
        SourceItem(
            url="https://www.youtube.com/watch?v=priority",
            title="Priority Video",
            source_type=SourceType.YOUTUBE,
            saved_at=datetime(2026, 5, 2, tzinfo=timezone.utc),
            inbox_provider="readwise",
            external_id="video",
            provider_content_mode=ProviderContentMode.EXTRACTED_CONTENT,
            pre_extracted_content=PreExtractedSourceContent(
                cleaned_text="Priority transcript.",
                raw_capture_kind="readwise_video",
                extraction_method="readwise",
            ),
        ),
        SourceItem(
            url="https://example.com/favorite",
            title="Favorite Article",
            source_type=SourceType.ARTICLE,
            tags=["favorite"],
            saved_at=datetime(2026, 5, 2, tzinfo=timezone.utc),
            inbox_provider="readwise",
            external_id="favorite",
            provider_content_mode=ProviderContentMode.EXTRACTED_CONTENT,
            pre_extracted_content=PreExtractedSourceContent(
                cleaned_text="Favorite evidence.",
                raw_capture_kind="readwise_article",
                extraction_method="readwise",
            ),
        ),
    ]
    connector = MagicMock()
    connector.connector_id = "readwise"
    connector.fetch_since.return_value = items

    def response_for_request(task, system_prompt, user_prompt, json_schema_hint=""):
        del task, system_prompt, json_schema_hint
        if "SourceType: youtube" in user_prompt:
            payload = {
                "quick_brief": "Video priority brief.",
                "best_next_action": "Use the transcript.",
                "consume_recommendation": "Transcript sufficient.",
                "key_ideas": ["Video was prioritized."],
                "takeaways": ["Skip playback."],
                "important_terms": ["Priority"],
                "topics": ["Priority"],
                "entities": [],
                "concepts": [],
                "watch_verdict": "transcript_sufficient",
                "watch_verdict_reasoning": "Transcript has the signal.",
                "quick_section_guide": "0:00 useful",
                "detailed_sections": "Useful opening.",
                "signal_vs_filler": "Mostly signal.",
            }
        else:
            payload = _article_brief_payload("Article priority brief.", "Article was prioritized.")
        return BackendResponse(
            text=json.dumps(payload),
            success=True,
            backend_used=BackendType.API,
            model_used="test-model",
        )

    with (
        patch("app.services.readwise_import_service.get_settings") as import_settings,
        patch("app.services.readwise_import_service.get_inbox_connector", return_value=connector),
        patch("app.services.readwise_import_service.Database") as ImportDB,
    ):
        import_settings.return_value.db_path = tmp_db._path
        import_settings.return_value.vault_path = tmp_vault
        import_settings.return_value.evidence_blob_dir = ".system/blobs"
        import_settings.return_value.evidence_blob_threshold_bytes = 50_000
        import_settings.return_value.evidence_blob_preview_chars = 4_000
        ImportDB.return_value = tmp_db
        await import_readwise_sources(limit=3)

    with (
        patch("app.services.brief_service.get_settings") as brief_settings,
        patch("app.services.brief_service.Database") as BriefDB,
        patch(
            "app.services.brief_service.run_structured",
            new_callable=AsyncMock,
            side_effect=response_for_request,
        ),
    ):
        brief_settings.return_value.db_path = tmp_db._path
        brief_settings.return_value.vault_path = tmp_vault
        brief_settings.return_value.evidence_blob_dir = ".system/blobs"
        brief_settings.return_value.evidence_blob_threshold_bytes = 50_000
        brief_settings.return_value.evidence_blob_preview_chars = 4_000
        BriefDB.return_value = tmp_db

        result = await compile_pending_source_briefs(limit=2)

    ready_titles = {
        source.title
        for source in SourceCatalogRepository(tmp_db).list_sources(display_state="brief_ready")
    }

    assert result.compiled_count == 2
    assert ready_titles == {"Priority Video", "Favorite Article"}


def _article_brief_payload(quick_brief: str, takeaway: str) -> dict:
    return {
        "quick_brief": quick_brief,
        "best_next_action": "Use the brief first.",
        "consume_recommendation": "Brief sufficient.",
        "key_ideas": ["Briefs support triage."],
        "takeaways": [takeaway],
        "important_terms": ["Source Brief"],
        "topics": ["Knowledge management"],
        "entities": [],
        "concepts": [],
        "read_verdict": "brief_sufficient",
        "why_read_or_skip": "The brief is enough for now.",
        "key_sections": ["Triage"],
    }
