"""Tests for summarize-first YouTube extraction behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.connectors.fetchers.summarize_cli import SummarizeResult
from app.models.source import SourceContent, SourceItem, SourceType


def _make_item() -> SourceItem:
    return SourceItem(
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        source_type=SourceType.YOUTUBE,
    )


def _settings() -> MagicMock:
    mock = MagicMock()
    mock.summarize_use_for_youtube_primary = True
    mock.summarize_prefer_markdown = True
    mock.summarize_weak_text_min_chars = 400
    mock.summarize_weak_paragraph_min_count = 2
    mock.summarize_weak_x_snippet_max_chars = 320
    mock.youtube_use_ytdlp_fallback = True
    mock.youtube_fetch_timeout_seconds = 30
    mock.youtube_transcript_max_chars = 0
    return mock


def _summarize_content(item: SourceItem, *, text: str, quality: str) -> SourceContent:
    return SourceContent(
        source=SourceItem(url=item.url, title="Summarized Video", source_type=item.source_type),
        cleaned_text=text,
        archived_markdown=f"# Summarized Video\n\n{text}",
        raw_capture_kind="summarize_youtube_extract",
        author="Summarize Channel",
        extraction_quality=quality,
        extraction_method="summarize_cli",
        raw_metadata={"transcript_source": "web"},
        canonical_url=item.url,
        url_hash="url-hash",
    )


@pytest.mark.asyncio
async def test_youtube_summarize_primary_success():
    item = _make_item()

    with (
        patch("app.connectors.fetchers.youtube.get_settings") as mock_settings,
        patch("app.connectors.fetchers.youtube.summarize_is_available") as mock_available,
        patch(
            "app.connectors.fetchers.youtube.summarize_extract_url",
            new_callable=AsyncMock,
        ) as mock_extract,
        patch(
            "app.connectors.fetchers.youtube.summarize_result_to_source_content"
        ) as mock_normalize,
        patch(
            "app.connectors.fetchers.youtube._try_transcript_api",
            new_callable=AsyncMock,
        ) as mock_transcript,
        patch(
            "app.connectors.fetchers.youtube._fetch_video_metadata",
            new_callable=AsyncMock,
        ) as mock_meta,
    ):
        mock_settings.return_value = _settings()
        mock_available.return_value = True
        mock_extract.return_value = SummarizeResult(success=True, cleaned_text="ignored")
        mock_normalize.return_value = _summarize_content(
            item,
            text=" ".join(["transcript"] * 250),
            quality="full",
        )
        mock_meta.return_value = ("Video Title", "Channel", "Description", "05:00")

        from app.connectors.fetchers.youtube import fetch_youtube

        result = await fetch_youtube(item)

    assert result.extraction_method == "summarize_cli"
    assert "summarize_cli" in result.extraction_fallback_chain
    assert mock_transcript.await_count == 0
    assert result.raw_capture_kind == "summarize_youtube_extract"


@pytest.mark.asyncio
async def test_youtube_summarize_failure_falls_back_to_transcript_api():
    item = _make_item()

    with (
        patch("app.connectors.fetchers.youtube.get_settings") as mock_settings,
        patch("app.connectors.fetchers.youtube.summarize_is_available") as mock_available,
        patch(
            "app.connectors.fetchers.youtube.summarize_extract_url",
            new_callable=AsyncMock,
        ) as mock_extract,
        patch(
            "app.connectors.fetchers.youtube._try_transcript_api",
            new_callable=AsyncMock,
        ) as mock_transcript,
        patch(
            "app.connectors.fetchers.youtube._fetch_video_metadata",
            new_callable=AsyncMock,
        ) as mock_meta,
    ):
        mock_settings.return_value = _settings()
        mock_available.return_value = True
        mock_extract.return_value = SummarizeResult(
            success=False,
            provider_notes="boom",
            extraction_method="summarize_cli",
        )
        mock_transcript.return_value = (
            " ".join(["word"] * 300),
            "youtube_transcript_api",
            False,
            "",
        )
        mock_meta.return_value = ("Video Title", "Channel", "Description", "05:00")

        from app.connectors.fetchers.youtube import fetch_youtube

        result = await fetch_youtube(item)

    assert result.extraction_method == "youtube_transcript_api"
    assert result.extraction_quality == "full"
    assert result.extraction_fallback_chain[:2] == ["summarize_cli", "youtube_transcript_api"]


@pytest.mark.asyncio
async def test_youtube_summarize_weak_output_uses_local_fallback():
    item = _make_item()

    with (
        patch("app.connectors.fetchers.youtube.get_settings") as mock_settings,
        patch("app.connectors.fetchers.youtube.summarize_is_available") as mock_available,
        patch(
            "app.connectors.fetchers.youtube.summarize_extract_url",
            new_callable=AsyncMock,
        ) as mock_extract,
        patch(
            "app.connectors.fetchers.youtube.summarize_result_to_source_content"
        ) as mock_normalize,
        patch(
            "app.connectors.fetchers.youtube._try_transcript_api",
            new_callable=AsyncMock,
        ) as mock_transcript,
        patch(
            "app.connectors.fetchers.youtube._fetch_video_metadata",
            new_callable=AsyncMock,
        ) as mock_meta,
    ):
        mock_settings.return_value = _settings()
        mock_available.return_value = True
        mock_extract.return_value = SummarizeResult(success=True, cleaned_text="ignored")
        mock_normalize.return_value = _summarize_content(
            item,
            text="short snippet",
            quality="partial",
        )
        mock_transcript.return_value = (
            " ".join(["word"] * 280),
            "youtube_transcript_api",
            False,
            "",
        )
        mock_meta.return_value = ("Video Title", "Channel", "Description", "05:00")

        from app.connectors.fetchers.youtube import fetch_youtube

        result = await fetch_youtube(item)

    assert result.extraction_method == "youtube_transcript_api"
    assert "summarize returned weak YouTube output" in result.extraction_notes
