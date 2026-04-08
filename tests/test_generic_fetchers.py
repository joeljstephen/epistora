"""Tests for generic page extraction with fallback chain."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.models.source import SourceContent, SourceItem, SourceType


def _make_item(url: str = "https://example.com/page") -> SourceItem:
    return SourceItem(url=url, source_type=SourceType.GENERIC)


GOOD_HTML = """
<html><head><title>Example Page</title>
<meta property="og:title" content="Example OG Title">
<meta property="og:description" content="OG description for test.">
</head><body>
<article>
<p>This is a well-written page about a fascinating topic. It contains enough
content to be considered a good extraction with multiple paragraphs.</p>
<p>The second paragraph provides additional detail about the subject matter,
including examples, references, and context that enriches understanding.</p>
<p>A third paragraph rounds out the content to ensure there's sufficient
word count for a full quality rating in the extraction system.</p>
</article></body></html>
"""


@pytest.mark.asyncio
async def test_generic_trafilatura_success():
    """Generic fetcher extracts content via trafilatura."""
    item = _make_item()

    with patch("app.connectors.fetchers.generic.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.text = GOOD_HTML
        mock_resp.raise_for_status = lambda: None
        mock_client.get.return_value = mock_resp

        from app.connectors.fetchers.generic import fetch_generic

        result = await fetch_generic(item)

    assert "trafilatura" in result.extraction_fallback_chain
    assert result.word_count > 0
    assert result.extraction_quality in ("full", "mostly_full", "partial")


@pytest.mark.asyncio
async def test_generic_http_failure():
    """HTTP failure returns failed result."""
    item = _make_item()

    with patch("app.connectors.fetchers.generic.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")

        from app.connectors.fetchers.generic import fetch_generic

        result = await fetch_generic(item)

    assert result.extraction_quality == "failed"


@pytest.mark.asyncio
async def test_generic_metadata_only_fallback():
    """When extractors fail, metadata-only content is used."""
    item = _make_item()

    with (
        patch("app.connectors.fetchers.generic.httpx.AsyncClient") as mock_client_cls,
        patch("app.connectors.fetchers.generic.trafilatura") as mock_traf,
        patch("app.connectors.fetchers.generic.extract_with_readability") as mock_read,
    ):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.text = (
            '<html><head><meta property="og:description" '
            'content="OG fallback content"></head></html>'
        )
        mock_resp.raise_for_status = lambda: None
        mock_client.get.return_value = mock_resp

        mock_traf.extract.return_value = ""
        mock_read.return_value = ("", "")

        from app.connectors.fetchers.generic import fetch_generic

        result = await fetch_generic(item)

    assert "metadata_only" in result.extraction_fallback_chain
    assert result.extraction_quality == "metadata_only"
    assert "OG fallback content" in result.cleaned_text


@pytest.mark.asyncio
async def test_article_tag_promotes_generic_source_to_article_fetcher():
    item = SourceItem(
        url="https://example.com/page",
        source_type=SourceType.GENERIC,
        tags=["article"],
    )

    with patch("app.connectors.fetchers.fetch_article", new_callable=AsyncMock) as mock_article:
        mock_article.return_value = SourceContent(
            source=SourceItem(
                url=item.url,
                title="Promoted Article",
                source_type=SourceType.ARTICLE,
                tags=item.tags,
            ),
            cleaned_text="Promoted article body",
            archived_markdown="# Promoted Article",
            raw_capture_kind="readable_article_markdown",
            extraction_quality="full",
            extraction_method="trafilatura",
            url_hash="promoted-url",
        )

        from app.connectors.fetchers import fetch_content

        result = await fetch_content(item)

    assert item.source_type == SourceType.ARTICLE
    assert mock_article.await_count == 1
    assert result.raw_capture_kind == "readable_article_markdown"
