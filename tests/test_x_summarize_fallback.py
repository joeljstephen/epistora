"""Tests for summarize fallback behavior in X extraction."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.connectors.fetchers.summarize_cli import SummarizeResult
from app.models.source import SourceContent, SourceItem, SourceType


def _item() -> SourceItem:
    return SourceItem(url="https://x.com/user/status/1234567890", source_type=SourceType.X_THREAD)


def _settings(**overrides) -> MagicMock:
    values = {
        "x_api_enabled": False,
        "x_api_bearer_token": "",
        "x_api_timeout_seconds": 30,
        "x_mirror_enabled": True,
        "x_mirror_timeout_seconds": 20,
        "x_oembed_enabled": True,
        "browser_fallback_enabled": False,
        "browser_fallback_timeout_seconds": 30,
        "summarize_use_for_x_fallback": True,
        "summarize_prefer_markdown": True,
        "summarize_weak_text_min_chars": 400,
        "summarize_weak_paragraph_min_count": 2,
        "summarize_weak_x_snippet_max_chars": 320,
    }
    values.update(overrides)
    mock = MagicMock()
    for key, value in values.items():
        setattr(mock, key, value)
    return mock


def _summarize_content(item: SourceItem) -> SourceContent:
    body = " ".join(["expanded"] * 180)
    return SourceContent(
        source=SourceItem(url=item.url, title="Expanded X Thread", source_type=item.source_type),
        cleaned_text=body,
        archived_markdown=f"# Expanded X Thread\n\n{body}",
        raw_capture_kind="summarize_x_extract",
        author="summarizer",
        extraction_quality="mostly_full",
        extraction_method="summarize_cli",
        canonical_url=item.url,
        url_hash="url-hash",
    )


@pytest.mark.asyncio
async def test_x_official_api_success_skips_summarize():
    item = _item()
    thread_text = " ".join(["thread"] * 180)

    with (
        patch("app.connectors.fetchers.x_thread.get_settings") as mock_settings,
        patch(
            "app.connectors.fetchers.x_thread._tier_official_api",
            new_callable=AsyncMock,
        ) as mock_api,
        patch(
            "app.connectors.fetchers.x_thread.summarize_extract_url",
            new_callable=AsyncMock,
        ) as mock_summarize,
    ):
        mock_settings.return_value = _settings(x_api_enabled=True, x_api_bearer_token="token")
        mock_api.return_value = {
            "text": thread_text,
            "author": "apiuser",
            "title": "@apiuser thread",
            "note": "Thread with 3 posts reconstructed via X API.",
            "metadata": {"post_id": "1234567890"},
        }

        from app.connectors.fetchers.x_thread import fetch_x_thread

        result = await fetch_x_thread(item)

    assert result.extraction_method == "x_api"
    assert mock_summarize.await_count == 0


@pytest.mark.asyncio
async def test_x_mirror_success_skips_summarize():
    item = _item()

    with (
        patch("app.connectors.fetchers.x_thread.get_settings") as mock_settings,
        patch(
            "app.connectors.fetchers.x_thread._tier_mirror_apis",
            new_callable=AsyncMock,
        ) as mock_mirror,
        patch(
            "app.connectors.fetchers.x_thread.summarize_extract_url",
            new_callable=AsyncMock,
        ) as mock_summarize,
    ):
        mock_settings.return_value = _settings()
        mock_mirror.return_value = {
            "text": " ".join(["mirror"] * 180),
            "author": "mirroruser",
            "source": "fxtwitter",
            "note": "Extracted via fxtwitter.",
            "metadata": {"source_api": "fxtwitter"},
        }

        from app.connectors.fetchers.x_thread import fetch_x_thread

        result = await fetch_x_thread(item)

    assert result.extraction_method == "fxtwitter"
    assert mock_summarize.await_count == 0


@pytest.mark.asyncio
async def test_x_weak_output_attempts_summarize_fallback():
    item = _item()

    with (
        patch("app.connectors.fetchers.x_thread.get_settings") as mock_settings,
        patch(
            "app.connectors.fetchers.x_thread._tier_mirror_apis",
            new_callable=AsyncMock,
        ) as mock_mirror,
        patch(
            "app.connectors.fetchers.x_thread._tier_oembed",
            new_callable=AsyncMock,
        ) as mock_oembed,
        patch("app.connectors.fetchers.x_thread.summarize_is_available") as mock_available,
        patch(
            "app.connectors.fetchers.x_thread.summarize_extract_url",
            new_callable=AsyncMock,
        ) as mock_summarize,
        patch(
            "app.connectors.fetchers.x_thread.summarize_result_to_source_content"
        ) as mock_normalize,
    ):
        mock_settings.return_value = _settings()
        mock_mirror.return_value = None
        mock_oembed.return_value = {
            "text": "short preview snippet",
            "author": "preview",
            "source": "oembed_noembed.com",
            "note": "Extracted via oEmbed.",
        }
        mock_available.return_value = True
        mock_summarize.return_value = SummarizeResult(success=True, cleaned_text="ignored")
        mock_normalize.return_value = _summarize_content(item)

        from app.connectors.fetchers.x_thread import fetch_x_thread

        result = await fetch_x_thread(item)

    assert result.extraction_method == "summarize_cli"
    assert "summarize_cli" in result.extraction_fallback_chain
    assert result.author == "summarizer"


@pytest.mark.asyncio
async def test_x_summarize_failure_still_uses_page_scrape():
    item = _item()

    with (
        patch("app.connectors.fetchers.x_thread.get_settings") as mock_settings,
        patch(
            "app.connectors.fetchers.x_thread._tier_mirror_apis",
            new_callable=AsyncMock,
        ) as mock_mirror,
        patch(
            "app.connectors.fetchers.x_thread._tier_oembed",
            new_callable=AsyncMock,
        ) as mock_oembed,
        patch("app.connectors.fetchers.x_thread.summarize_is_available") as mock_available,
        patch(
            "app.connectors.fetchers.x_thread.summarize_extract_url",
            new_callable=AsyncMock,
        ) as mock_summarize,
        patch(
            "app.connectors.fetchers.x_thread._tier_page_scrape",
            new_callable=AsyncMock,
        ) as mock_page,
    ):
        mock_settings.return_value = _settings()
        mock_mirror.return_value = None
        mock_oembed.return_value = None
        mock_available.return_value = True
        mock_summarize.return_value = SummarizeResult(success=False, provider_notes="failed")
        mock_page.return_value = {"text": " ".join(["page"] * 160), "title": "Page Scrape"}

        from app.connectors.fetchers.x_thread import fetch_x_thread

        result = await fetch_x_thread(item)

    assert result.extraction_method == "page_scrape"
    assert "summarize fallback failed" in result.extraction_notes
