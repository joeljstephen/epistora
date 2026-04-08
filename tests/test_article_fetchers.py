"""Tests for article extraction with fallback chain."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.models.source import SourceItem, SourceType


def _make_item(url: str = "https://example.com/article") -> SourceItem:
    return SourceItem(url=url, source_type=SourceType.ARTICLE)


RICH_HTML = """
<html><head><title>Test Article</title>
<meta property="og:title" content="OG Title">
<meta property="og:description" content="OG description text.">
<link rel="canonical" href="https://example.com/canonical">
</head><body>
<article>
<p>This is a substantial article about testing in Python. It covers many topics
including unit tests, integration tests, mocking, fixtures, and best practices.
We explore how to write maintainable tests that provide confidence in your code.
The article discusses the fundamental principles of software testing and why
every developer should understand how to write effective test suites. Testing
is not just about finding bugs, it is about building confidence in the code
and enabling refactoring without fear. Modern Python testing frameworks like
pytest make it easy to write expressive and readable test cases.</p>
<p>Second paragraph adds more content about test-driven development, continuous
integration, and the importance of code coverage metrics in modern software projects.
Test-driven development is a discipline that requires writing tests before code,
ensuring that every piece of functionality is covered. Continuous integration
pipelines run tests automatically on every commit, providing rapid feedback
to developers. Code coverage tools measure which lines of code are exercised
by the test suite, helping teams identify gaps in their testing strategy.
Together these practices form the foundation of reliable software delivery.</p>
</article></body></html>
"""

SHORT_HTML = """
<html><head><title>Short</title></head><body><p>Just a tiny snippet.</p></body></html>
"""


@pytest.mark.asyncio
async def test_article_trafilatura_success():
    """Trafilatura extracts good content on first try."""
    item = _make_item()

    with patch("app.connectors.fetchers.article._fetch_html", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = RICH_HTML

        from app.connectors.fetchers.article import fetch_article

        result = await fetch_article(item)

    assert result.extraction_quality in ("full", "mostly_full")
    assert "trafilatura" in result.extraction_fallback_chain
    assert result.extraction_method == "trafilatura"
    assert result.canonical_url == "https://example.com/canonical"
    assert result.word_count > 0
    assert result.raw_capture_kind == "readable_article_markdown"
    assert "# Test Article" in result.archived_markdown or "# OG Title" in result.archived_markdown


@pytest.mark.asyncio
async def test_article_readability_fallback():
    """When trafilatura returns weak content, readability fallback kicks in."""
    item = _make_item()

    with (
        patch("app.connectors.fetchers.article._fetch_html", new_callable=AsyncMock) as mock_fetch,
        patch("app.connectors.fetchers.article._try_trafilatura") as mock_traf,
        patch("app.connectors.fetchers.article.extract_with_readability") as mock_read,
    ):
        mock_fetch.return_value = SHORT_HTML
        mock_traf.return_value = ("tiny", "", "", "trafilatura")
        mock_read.return_value = (
            "A much longer readability extraction with enough words " * 10,
            "Readability Title",
        )

        from app.connectors.fetchers.article import fetch_article

        result = await fetch_article(item)

    assert result.extraction_method == "readability"
    assert "readability" in result.extraction_fallback_chain
    assert "Readability" in result.extraction_notes or result.word_count > 10


@pytest.mark.asyncio
async def test_article_metadata_only_fallback():
    """When all extractors fail, metadata-only fallback captures OG tags."""
    item = _make_item()

    with (
        patch("app.connectors.fetchers.article._fetch_html", new_callable=AsyncMock) as mock_fetch,
        patch("app.connectors.fetchers.article._try_trafilatura") as mock_traf,
        patch("app.connectors.fetchers.article.extract_with_readability") as mock_read,
    ):
        mock_fetch.return_value = (
            '<html><head><meta property="og:description" '
            'content="OG fallback text"></head><body></body></html>'
        )
        mock_traf.return_value = ("", "", "", "trafilatura")
        mock_read.return_value = ("", "")

        from app.connectors.fetchers.article import fetch_article

        result = await fetch_article(item)

    assert "metadata_only" in result.extraction_fallback_chain
    assert result.extraction_quality == "metadata_only"
    assert result.extraction_method == "metadata_only"
    assert "OG fallback text" in result.cleaned_text


@pytest.mark.asyncio
async def test_article_http_failure():
    """HTTP failure returns a failed result."""
    item = _make_item()

    with patch("app.connectors.fetchers.article._fetch_html", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = None

        from app.connectors.fetchers.article import fetch_article

        result = await fetch_article(item)

    assert result.extraction_quality == "failed"


@pytest.mark.asyncio
async def test_article_browser_fallback_mocked():
    """Browser fallback is attempted when earlier extractors fail and config enables it."""
    item = _make_item()

    with (
        patch("app.connectors.fetchers.article._fetch_html", new_callable=AsyncMock) as mock_fetch,
        patch("app.connectors.fetchers.article._try_trafilatura") as mock_traf,
        patch("app.connectors.fetchers.article.extract_with_readability") as mock_read,
        patch("app.connectors.fetchers.article.is_browser_available") as mock_avail,
        patch(
            "app.connectors.fetchers.article.fetch_rendered_html",
            new_callable=AsyncMock,
        ) as mock_browser,
        patch("app.connectors.fetchers.article.get_settings") as mock_settings,
    ):
        settings = mock_settings.return_value
        settings.article_fetch_timeout_seconds = 30
        settings.article_use_readability_fallback = True
        settings.article_use_browser_fallback = True
        settings.browser_fallback_enabled = True
        settings.browser_fallback_timeout_seconds = 30

        mock_fetch.return_value = SHORT_HTML
        mock_traf.side_effect = [
            ("tiny", "", "", "trafilatura"),
            ("A browser recovered extraction with enough words " * 10, "", "", "trafilatura"),
        ]
        mock_read.return_value = ("", "")
        mock_avail.return_value = True
        mock_browser.return_value = RICH_HTML

        from app.connectors.fetchers.article import fetch_article

        result = await fetch_article(item)

    assert "browser_rendered" in result.extraction_fallback_chain
    assert result.extraction_method == "browser_rendered+trafilatura"
