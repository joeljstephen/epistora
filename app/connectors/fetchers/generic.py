"""Generic page extraction fallback with multi-tier chain.

Fallback order:
1. Trafilatura
2. readability-lxml
3. Browser-rendered (optional)
4. Metadata-only
"""

from __future__ import annotations

import logging

import httpx
import trafilatura
from bs4 import BeautifulSoup

from app.config import get_settings
from app.connectors.fetchers.browser import fetch_rendered_html, is_browser_available
from app.connectors.fetchers.readability import extract_with_readability
from app.models.source import SourceContent, SourceItem
from app.utils.extraction import (
    extract_og_metadata,
    normalize_whitespace,
    resolve_canonical_url,
    score_extraction_quality,
)
from app.utils.hashing import content_hash, url_hash
from app.utils.http import assert_safe_http_url

logger = logging.getLogger(__name__)


async def fetch_generic(item: SourceItem) -> SourceContent:
    """Fallback fetcher: try readable text extraction from any URL."""
    settings = get_settings()
    fallback_chain: list[str] = []
    notes_parts: list[str] = []

    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=settings.article_fetch_timeout_seconds
        ) as client:
            resp = await client.get(item.url)
            resp.raise_for_status()
            response_url = (
                resp.url if isinstance(getattr(resp, "url", None), str | httpx.URL) else item.url
            )
            assert_safe_http_url(str(response_url))
            html = resp.text
    except Exception as e:
        return SourceContent(
            source=item,
            extraction_quality="failed",
            extraction_method="none",
            extraction_fallback_chain=["http_failed"],
            extraction_notes=f"HTTP fetch failed: {e}",
            url_hash=url_hash(item.url),
        )

    og_meta = extract_og_metadata(html)
    canonical = resolve_canonical_url(html, item.url)
    method = ""

    extracted = trafilatura.extract(html, include_comments=False, include_tables=True) or ""
    fallback_chain.append("trafilatura")
    method = "trafilatura"

    if len(extracted) < 200:
        readability_text, readability_title = extract_with_readability(html)
        fallback_chain.append("readability")
        if len(readability_text) > len(extracted):
            extracted = readability_text
            method = "readability"
            if readability_title and not item.title:
                item.title = readability_title
            notes_parts.append("Readability fallback improved extraction.")

    if (
        len(extracted) < 200
        and settings.browser_fallback_enabled
        and is_browser_available()
    ):
        rendered = await fetch_rendered_html(
            item.url, timeout_ms=settings.browser_fallback_timeout_seconds * 1000
        )
        fallback_chain.append("browser_rendered")
        if rendered:
            browser_text, browser_method = _extract_best_text(rendered)
            if len(browser_text) > len(extracted):
                extracted = browser_text
                method = f"browser_rendered+{browser_method}"
                notes_parts.append("Browser rendering improved extraction.")

    if not extracted:
        fallback_chain.append("metadata_only")
        method = "metadata_only"
        extracted = og_meta.get("og_description") or og_meta.get("description") or ""
        notes_parts.append("All extractors failed; generic metadata-only fallback.")

    extracted = normalize_whitespace(extracted)

    if not item.title:
        item.title = og_meta.get("og_title") or og_meta.get("page_title") or ""
    if not item.title:
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        item.title = (title_tag.get_text(strip=True) if title_tag else "") or item.url

    quality = score_extraction_quality(
        extracted,
        has_title=bool(item.title),
        is_metadata_only=(method == "metadata_only"),
    )

    return SourceContent(
        source=item,
        raw_text=html[:50000],
        cleaned_text=extracted,
        word_count=len(extracted.split()) if extracted else 0,
        extraction_quality=quality.value,
        extraction_method=method,
        extraction_fallback_chain=fallback_chain,
        extraction_notes=" ".join(notes_parts),
        raw_metadata=og_meta,
        canonical_url=canonical,
        content_hash=content_hash(extracted) if extracted else "",
        url_hash=url_hash(item.url),
    )


def _extract_best_text(html: str) -> tuple[str, str]:
    """Extract readable text from HTML, preferring trafilatura then readability."""
    trafilatura_text = (
        trafilatura.extract(html, include_comments=False, include_tables=True) or ""
    )
    readability_text, _ = extract_with_readability(html)

    if len(readability_text) > len(trafilatura_text):
        return readability_text, "readability"

    return trafilatura_text, "trafilatura"
