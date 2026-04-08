"""Tests for summarize fallback in generic extraction."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.connectors.fetchers.summarize_cli import SummarizeResult
from app.models.source import SourceContent, SourceItem, SourceType


def _item() -> SourceItem:
    return SourceItem(url="https://example.com/page", source_type=SourceType.GENERIC)


def _settings(**overrides) -> MagicMock:
    values = {
        "article_fetch_timeout_seconds": 30,
        "browser_fallback_enabled": False,
        "browser_fallback_timeout_seconds": 30,
        "summarize_use_for_generic_fallback": True,
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


def _response(html: str) -> AsyncMock:
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.text = html
    mock_resp.raise_for_status = lambda: None
    return mock_resp


def _summarize_content(item: SourceItem) -> SourceContent:
    body = " ".join(["summarize"] * 220)
    return SourceContent(
        source=SourceItem(url=item.url, title="Summarized Generic", source_type=item.source_type),
        cleaned_text=body,
        archived_markdown=f"# Summarized Generic\n\n{body}",
        raw_capture_kind="summarize_generic_extract",
        extraction_quality="full",
        extraction_method="summarize_cli",
        canonical_url=item.url,
        url_hash="url-hash",
    )


@pytest.mark.asyncio
async def test_generic_summarize_fallback_improves_weak_extraction():
    item = _item()
    weak_html = "<html><head><title>Short</title></head><body><p>Tiny.</p></body></html>"

    with (
        patch("app.connectors.fetchers.generic.get_settings") as mock_settings,
        patch("app.connectors.fetchers.generic.httpx.AsyncClient") as mock_client_cls,
        patch("app.connectors.fetchers.generic.trafilatura") as mock_traf,
        patch("app.connectors.fetchers.generic.extract_with_readability") as mock_read,
        patch("app.connectors.fetchers.generic.summarize_is_available") as mock_available,
        patch(
            "app.connectors.fetchers.generic.summarize_extract_url",
            new_callable=AsyncMock,
        ) as mock_summarize,
        patch(
            "app.connectors.fetchers.generic.summarize_result_to_source_content"
        ) as mock_normalize,
    ):
        mock_settings.return_value = _settings()
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get.return_value = _response(weak_html)
        mock_traf.extract.return_value = "tiny"
        mock_read.return_value = ("", "")
        mock_available.return_value = True
        mock_summarize.return_value = SummarizeResult(success=True, cleaned_text="ignored")
        mock_normalize.return_value = _summarize_content(item)

        from app.connectors.fetchers.generic import fetch_generic

        result = await fetch_generic(item)

    assert result.extraction_method == "summarize_cli"
    assert result.raw_capture_kind == "summarize_generic_extract"
    assert result.archived_markdown.startswith("# Summarized Generic")


@pytest.mark.asyncio
async def test_generic_summarize_unavailable_keeps_existing_path():
    item = _item()
    good_html = """
    <html><head><title>Example Page</title></head><body>
    <article><p>This page has enough text to pass extraction quality heuristics comfortably.</p>
    <p>Second paragraph keeps the result strong enough that summarize is unnecessary.</p></article>
    </body></html>
    """

    with (
        patch("app.connectors.fetchers.generic.get_settings") as mock_settings,
        patch("app.connectors.fetchers.generic.httpx.AsyncClient") as mock_client_cls,
        patch("app.connectors.fetchers.generic.summarize_is_available") as mock_available,
        patch(
            "app.connectors.fetchers.generic.summarize_extract_url",
            new_callable=AsyncMock,
        ) as mock_summarize,
    ):
        mock_settings.return_value = _settings()
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_client.get.return_value = _response(good_html)
        mock_available.return_value = False

        from app.connectors.fetchers.generic import fetch_generic

        result = await fetch_generic(item)

    assert result.extraction_method == "trafilatura"
    assert mock_summarize.await_count == 0
