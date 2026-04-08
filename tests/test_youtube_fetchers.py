"""Tests for YouTube extraction with fallback chain."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.models.source import SourceItem, SourceType


def _make_item(url: str = "https://www.youtube.com/watch?v=dQw4w9WgXcQ") -> SourceItem:
    return SourceItem(url=url, source_type=SourceType.YOUTUBE)


@pytest.mark.asyncio
async def test_youtube_video_id_parsing():
    """Various YouTube URL formats are parsed correctly."""
    from app.connectors.fetchers.youtube import _extract_video_id

    cases = [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/v/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://example.com/no-video", None),
    ]
    for url, expected in cases:
        assert _extract_video_id(url) == expected, f"Failed for {url}"


@pytest.mark.asyncio
async def test_youtube_invalid_url():
    """Invalid URL returns failed result."""
    item = _make_item("https://example.com/not-youtube")

    from app.connectors.fetchers.youtube import fetch_youtube

    result = await fetch_youtube(item)
    assert result.extraction_quality == "failed"


@pytest.mark.asyncio
async def test_youtube_transcript_api_success():
    """Transcript API succeeds and returns full quality."""
    item = _make_item()

    mock_transcript = " ".join(["word"] * 300)

    with (
        patch(
            "app.connectors.fetchers.youtube._try_transcript_api",
            new_callable=AsyncMock,
        ) as mock_api,
        patch(
            "app.connectors.fetchers.youtube._fetch_video_metadata",
            new_callable=AsyncMock,
        ) as mock_meta,
    ):
        mock_api.return_value = (mock_transcript, "youtube_transcript_api", False, "")
        mock_meta.return_value = ("Test Video", "Test Channel", "Description", "5:30")

        from app.connectors.fetchers.youtube import fetch_youtube

        result = await fetch_youtube(item)

    assert result.extraction_quality == "full"
    assert result.extraction_method == "youtube_transcript_api"
    assert "youtube_transcript_api" in result.extraction_fallback_chain
    assert result.author == "Test Channel"
    assert result.word_count >= 300
    assert result.raw_capture_kind == "youtube_transcript"
    assert "## Transcript" in result.archived_markdown


@pytest.mark.asyncio
async def test_youtube_transcript_fail_ytdlp_fallback():
    """When transcript API fails, yt-dlp fallback is attempted."""
    item = _make_item()

    with (
        patch(
            "app.connectors.fetchers.youtube._try_transcript_api",
            new_callable=AsyncMock,
        ) as mock_api,
        patch(
            "app.connectors.fetchers.youtube._try_ytdlp",
        ) as mock_ytdlp,
        patch(
            "app.connectors.fetchers.youtube._fetch_video_metadata",
            new_callable=AsyncMock,
        ) as mock_meta,
        patch("app.connectors.fetchers.youtube.shutil") as mock_shutil,
    ):
        mock_api.return_value = ("", "", False, "API failed")
        mock_shutil.which.return_value = "/usr/bin/yt-dlp"
        mock_ytdlp.return_value = (
            " ".join(["subtitle"] * 200),
            "yt_dlp",
            True,
            "Extracted via yt-dlp (auto-caption).",
        )
        mock_meta.return_value = ("Test Video", "Channel", "", "")

        from app.connectors.fetchers.youtube import fetch_youtube

        result = await fetch_youtube(item)

    assert result.extraction_quality == "mostly_full"
    assert "yt_dlp" in result.extraction_fallback_chain


@pytest.mark.asyncio
async def test_youtube_all_fail_metadata_only():
    """When all transcript sources fail, result is metadata-only."""
    item = _make_item()

    with (
        patch(
            "app.connectors.fetchers.youtube._try_transcript_api",
            new_callable=AsyncMock,
        ) as mock_api,
        patch(
            "app.connectors.fetchers.youtube._fetch_video_metadata",
            new_callable=AsyncMock,
        ) as mock_meta,
        patch("app.connectors.fetchers.youtube.shutil") as mock_shutil,
    ):
        mock_api.return_value = ("", "", False, "No transcripts")
        mock_shutil.which.return_value = None
        mock_meta.return_value = ("Test Video", "Channel", "Desc", "3:45")

        from app.connectors.fetchers.youtube import fetch_youtube

        result = await fetch_youtube(item)

    assert result.extraction_quality == "metadata_only"
    assert "metadata_only" in result.extraction_fallback_chain
    assert result.extraction_method == "metadata_only"
    assert "Transcript: unavailable" in result.archived_markdown


@pytest.mark.asyncio
async def test_youtube_vtt_parsing():
    """VTT subtitle files are parsed into clean text."""
    from app.connectors.fetchers.youtube import _parse_vtt

    vtt = """WEBVTT

00:00:01.000 --> 00:00:03.000
Hello world

00:00:03.000 --> 00:00:06.000
This is a test

00:00:06.000 --> 00:00:09.000
Hello world
"""
    text = _parse_vtt(vtt)
    assert "Hello world" in text
    assert "This is a test" in text
    assert text.count("Hello world") == 1  # deduplication
