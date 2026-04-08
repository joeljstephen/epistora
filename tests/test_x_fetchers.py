"""Tests for X/Twitter extraction with five-tier fallback chain."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.source import SourceItem, SourceType


def _make_item(url: str = "https://x.com/user/status/1234567890") -> SourceItem:
    return SourceItem(url=url, source_type=SourceType.X_THREAD)


def _mock_settings(**overrides):
    defaults = {
        "x_api_enabled": False,
        "x_api_bearer_token": "",
        "x_api_timeout_seconds": 30,
        "x_mirror_enabled": True,
        "x_mirror_timeout_seconds": 20,
        "x_oembed_enabled": True,
        "browser_fallback_enabled": False,
        "browser_fallback_timeout_seconds": 30,
    }
    defaults.update(overrides)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


@pytest.mark.asyncio
async def test_x_api_success():
    """Official X API returns full thread content when configured."""
    item = _make_item()
    thread_text = (
        "This is the first post in a long thread about software architecture. "
        "It discusses the importance of clean separation of concerns and modular design.\n\n"
        "The second post continues with specific examples of how to apply these principles "
        "in real-world Python projects using dependency injection and layered architectures.\n\n"
        "The third post wraps up the thread with recommendations for tools and frameworks "
        "that help enforce these patterns and make codebases easier to maintain over time."
    )

    with (
        patch("app.connectors.fetchers.x_thread.get_settings") as mock_gs,
        patch(
            "app.connectors.fetchers.x_thread._tier_official_api",
            new_callable=AsyncMock,
        ) as mock_api,
    ):
        mock_gs.return_value = _mock_settings(
            x_api_enabled=True, x_api_bearer_token="test-token"
        )
        mock_api.return_value = {
            "text": thread_text,
            "author": "testuser",
            "title": "@testuser — Thread post 1...",
            "note": "Thread with 3 posts reconstructed via X API.",
            "metadata": {"post_id": "1234567890", "thread_length": 3},
        }

        from app.connectors.fetchers.x_thread import fetch_x_thread

        result = await fetch_x_thread(item)

    assert result.extraction_method == "x_api"
    assert "x_api" in result.extraction_fallback_chain
    assert result.author == "testuser"
    assert "Thread" in result.extraction_notes
    assert result.extraction_quality in ("full", "mostly_full", "partial")


@pytest.mark.asyncio
async def test_x_no_api_mirror_fallback():
    """When API is not configured, mirror APIs are used."""
    item = _make_item()

    with (
        patch("app.connectors.fetchers.x_thread.get_settings") as mock_gs,
        patch(
            "app.connectors.fetchers.x_thread._tier_mirror_apis",
            new_callable=AsyncMock,
        ) as mock_mirrors,
    ):
        mock_gs.return_value = _mock_settings()
        mock_mirrors.return_value = {
            "text": "This is the full tweet content from fxtwitter with enough words " * 5,
            "author": "tweetauthor",
            "source": "fxtwitter",
            "note": "Extracted via fxtwitter.",
            "metadata": {"source_api": "fxtwitter"},
        }

        from app.connectors.fetchers.x_thread import fetch_x_thread

        result = await fetch_x_thread(item)

    assert result.extraction_method == "fxtwitter"
    assert "mirror_apis" in result.extraction_fallback_chain
    assert result.author == "tweetauthor"


@pytest.mark.asyncio
async def test_x_fxtwitter_fail_vxtwitter_success():
    """fxtwitter fails, vxtwitter succeeds."""
    item = _make_item()

    with (
        patch("app.connectors.fetchers.x_thread.get_settings") as mock_gs,
        patch(
            "app.connectors.fetchers.x_mirrors.fetch_via_fxtwitter",
            new_callable=AsyncMock,
        ) as mock_fx,
        patch(
            "app.connectors.fetchers.x_mirrors.fetch_via_vxtwitter",
            new_callable=AsyncMock,
        ) as mock_vx,
    ):
        mock_gs.return_value = _mock_settings()
        mock_fx.return_value = None
        mock_vx.return_value = {
            "text": "Content from vxtwitter with enough useful words for testing " * 4,
            "author_name": "vxauthor",
            "username": "vxuser",
            "source": "vxtwitter",
        }

        from app.connectors.fetchers.x_thread import _tier_mirror_apis

        result = await _tier_mirror_apis(item.url, 20)

    assert result is not None
    assert result["source"] == "vxtwitter"


@pytest.mark.asyncio
async def test_x_mirror_fail_oembed_fallback():
    """Mirrors fail, oEmbed fallback captures text."""
    item = _make_item()

    with (
        patch("app.connectors.fetchers.x_thread.get_settings") as mock_gs,
        patch(
            "app.connectors.fetchers.x_thread._tier_mirror_apis",
            new_callable=AsyncMock,
        ) as mock_mirrors,
        patch(
            "app.connectors.fetchers.x_thread._tier_oembed",
            new_callable=AsyncMock,
        ) as mock_oembed,
    ):
        mock_gs.return_value = _mock_settings()
        mock_mirrors.return_value = None
        mock_oembed.return_value = {
            "text": "oEmbed extracted tweet content with useful information about the topic " * 3,
            "author": "oembedauthor",
            "source": "oembed_noembed.com",
            "note": "Extracted via oEmbed (noembed.com).",
        }

        from app.connectors.fetchers.x_thread import fetch_x_thread

        result = await fetch_x_thread(item)

    assert "oembed" in result.extraction_fallback_chain
    assert result.author == "oembedauthor"


@pytest.mark.asyncio
async def test_x_total_failure_metadata_only():
    """All tiers fail — result is metadata_only."""
    item = _make_item()

    with (
        patch("app.connectors.fetchers.x_thread.get_settings") as mock_gs,
        patch(
            "app.connectors.fetchers.x_thread._tier_mirror_apis",
            new_callable=AsyncMock,
        ) as mock_mirrors,
        patch(
            "app.connectors.fetchers.x_thread._tier_oembed",
            new_callable=AsyncMock,
        ) as mock_oembed,
        patch(
            "app.connectors.fetchers.x_thread._tier_page_scrape",
            new_callable=AsyncMock,
        ) as mock_scrape,
    ):
        mock_gs.return_value = _mock_settings()
        mock_mirrors.return_value = None
        mock_oembed.return_value = None
        mock_scrape.return_value = None

        from app.connectors.fetchers.x_thread import fetch_x_thread

        result = await fetch_x_thread(item)

    assert result.extraction_quality == "metadata_only"
    assert "metadata_only" in result.extraction_fallback_chain
    assert "All X extraction" in result.extraction_notes


@pytest.mark.asyncio
async def test_x_thread_normalized_output_shape():
    """Result has all expected extraction metadata fields."""
    item = _make_item()

    with (
        patch("app.connectors.fetchers.x_thread.get_settings") as mock_gs,
        patch(
            "app.connectors.fetchers.x_thread._tier_mirror_apis",
            new_callable=AsyncMock,
        ) as mock_mirrors,
    ):
        mock_gs.return_value = _mock_settings()
        mock_mirrors.return_value = {
            "text": "Some tweet content that is long enough for partial " * 3,
            "author": "testauthor",
            "source": "fxtwitter",
            "note": "Extracted via fxtwitter.",
            "metadata": {"username": "testauthor"},
        }

        from app.connectors.fetchers.x_thread import fetch_x_thread

        result = await fetch_x_thread(item)

    assert result.extraction_method
    assert isinstance(result.extraction_fallback_chain, list)
    valid_qualities = ("full", "mostly_full", "partial", "metadata_only", "failed")
    assert result.extraction_quality in valid_qualities
    assert result.url_hash
    assert result.source.source_type == SourceType.X_THREAD


@pytest.mark.asyncio
async def test_x_post_id_extraction():
    """Post ID is correctly extracted from URL."""
    from app.connectors.fetchers.x_thread import _extract_post_id

    assert _extract_post_id("https://x.com/user/status/1234567890") == "1234567890"
    assert _extract_post_id("https://twitter.com/user/status/9876543210") == "9876543210"
    assert _extract_post_id("https://x.com/user") is None
    assert _extract_post_id("https://example.com") is None


@pytest.mark.asyncio
async def test_x_api_thread_assembly():
    """Thread text is assembled correctly from multiple tweets."""
    from app.connectors.fetchers.x_api import assemble_thread_text

    thread = [
        {"text": "First tweet in thread"},
        {"text": "Second tweet continues"},
        {"text": "Final tweet wraps up"},
    ]
    text = assemble_thread_text(thread)
    assert "[1/3]" in text
    assert "[2/3]" in text
    assert "[3/3]" in text
    assert "First tweet" in text
    assert "Final tweet" in text


@pytest.mark.asyncio
async def test_x_api_single_tweet_no_numbering():
    """Single tweet has no numbering prefix."""
    from app.connectors.fetchers.x_api import assemble_thread_text

    thread = [{"text": "Just a single tweet"}]
    text = assemble_thread_text(thread)
    assert "[1/1]" not in text
    assert "Just a single tweet" in text
