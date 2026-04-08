"""Tests for summarize fallback in article extraction."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.connectors.fetchers.summarize_cli import SummarizeResult
from app.models.source import SourceContent, SourceItem, SourceType

RICH_HTML = """
<html><head><title>Test Article</title></head><body>
<article>
<p>This article has enough text to satisfy the local extractor without any need
for summarize. It contains multiple paragraphs and enough useful words to cross
the minimum quality thresholds in the fetcher.</p>
<p>The second paragraph keeps the extraction comfortably above the weak-content
threshold and should prevent any summarize fallback attempt from happening in
this test.</p>
</article></body></html>
"""

SHORT_HTML = "<html><head><title>Short</title></head><body><p>Tiny.</p></body></html>"


def _item() -> SourceItem:
    return SourceItem(url="https://example.com/article", source_type=SourceType.ARTICLE)


def _settings(**overrides) -> MagicMock:
    values = {
        "article_fetch_timeout_seconds": 30,
        "article_use_readability_fallback": True,
        "article_use_browser_fallback": False,
        "browser_fallback_enabled": False,
        "browser_fallback_timeout_seconds": 30,
        "summarize_use_for_article_fallback": True,
        "summarize_prefer_markdown": True,
        "summarize_weak_text_min_chars": 120,
        "summarize_weak_paragraph_min_count": 2,
        "summarize_weak_x_snippet_max_chars": 320,
    }
    values.update(overrides)
    mock = MagicMock()
    for key, value in values.items():
        setattr(mock, key, value)
    return mock


def _summarize_content(item: SourceItem) -> SourceContent:
    body = " ".join(["summarize"] * 220)
    return SourceContent(
        source=SourceItem(url=item.url, title="Summarized Article", source_type=item.source_type),
        cleaned_text=body,
        archived_markdown=f"# Summarized Article\n\n{body}",
        raw_capture_kind="summarize_article_extract",
        author="Summarize Author",
        extraction_quality="full",
        extraction_method="summarize_cli",
        canonical_url=item.url,
        url_hash="url-hash",
    )


@pytest.mark.asyncio
async def test_article_strong_local_extraction_skips_summarize():
    item = _item()

    with (
        patch("app.connectors.fetchers.article.get_settings") as mock_settings,
        patch("app.connectors.fetchers.article._fetch_html", new_callable=AsyncMock) as mock_fetch,
        patch(
            "app.connectors.fetchers.article.summarize_extract_url",
            new_callable=AsyncMock,
        ) as mock_summarize,
        patch("app.connectors.fetchers.article.summarize_is_available") as mock_available,
    ):
        mock_settings.return_value = _settings()
        mock_fetch.return_value = RICH_HTML
        mock_available.return_value = True

        from app.connectors.fetchers.article import fetch_article

        result = await fetch_article(item)

    assert result.extraction_method == "trafilatura"
    assert mock_summarize.await_count == 0


@pytest.mark.asyncio
async def test_article_weak_local_extraction_uses_summarize_fallback():
    item = _item()

    with (
        patch("app.connectors.fetchers.article.get_settings") as mock_settings,
        patch("app.connectors.fetchers.article._fetch_html", new_callable=AsyncMock) as mock_fetch,
        patch("app.connectors.fetchers.article._try_trafilatura") as mock_traf,
        patch("app.connectors.fetchers.article.extract_with_readability") as mock_read,
        patch("app.connectors.fetchers.article.summarize_is_available") as mock_available,
        patch(
            "app.connectors.fetchers.article.summarize_extract_url",
            new_callable=AsyncMock,
        ) as mock_summarize,
        patch(
            "app.connectors.fetchers.article.summarize_result_to_source_content"
        ) as mock_normalize,
    ):
        mock_settings.return_value = _settings()
        mock_fetch.return_value = SHORT_HTML
        mock_traf.return_value = ("tiny", "", "", "", "trafilatura")
        mock_read.return_value = ("", "")
        mock_available.return_value = True
        mock_summarize.return_value = SummarizeResult(success=True, cleaned_text="ignored")
        mock_normalize.return_value = _summarize_content(item)

        from app.connectors.fetchers.article import fetch_article

        result = await fetch_article(item)

    assert result.extraction_method == "summarize_cli"
    assert "summarize_cli" in result.extraction_fallback_chain
    assert "summarize replaced weak local extraction" in result.extraction_notes


@pytest.mark.asyncio
async def test_article_summarize_failure_still_allows_browser_fallback():
    item = _item()

    with (
        patch("app.connectors.fetchers.article.get_settings") as mock_settings,
        patch("app.connectors.fetchers.article._fetch_html", new_callable=AsyncMock) as mock_fetch,
        patch("app.connectors.fetchers.article._try_trafilatura") as mock_traf,
        patch("app.connectors.fetchers.article.extract_with_readability") as mock_read,
        patch("app.connectors.fetchers.article.summarize_is_available") as mock_available,
        patch(
            "app.connectors.fetchers.article.summarize_extract_url",
            new_callable=AsyncMock,
        ) as mock_summarize,
        patch("app.connectors.fetchers.article.is_browser_available") as mock_browser_available,
        patch(
            "app.connectors.fetchers.article.fetch_rendered_html",
            new_callable=AsyncMock,
        ) as mock_browser,
    ):
        mock_settings.return_value = _settings(
            article_use_browser_fallback=True,
            browser_fallback_enabled=True,
        )
        mock_fetch.return_value = SHORT_HTML
        mock_traf.side_effect = [
            ("tiny", "", "", "", "trafilatura"),
            (" ".join(["browser"] * 220), "", "", "", "trafilatura"),
        ]
        mock_read.return_value = ("", "")
        mock_available.return_value = True
        mock_summarize.return_value = SummarizeResult(success=False, provider_notes="failed")
        mock_browser_available.return_value = True
        mock_browser.return_value = RICH_HTML

        from app.connectors.fetchers.article import fetch_article

        result = await fetch_article(item)

    assert result.extraction_method == "browser_rendered+trafilatura"
    assert "summarize_cli" in result.extraction_fallback_chain
    assert "browser_rendered" in result.extraction_fallback_chain
