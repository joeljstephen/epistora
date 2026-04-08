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
from app.connectors.fetchers.summarize_cli import (
    extract_url as summarize_extract_url,
)
from app.connectors.fetchers.summarize_cli import (
    is_available as summarize_is_available,
)
from app.connectors.fetchers.summarize_cli import (
    summarize_result_to_source_content,
)
from app.models.source import SourceContent, SourceItem
from app.utils.extraction import (
    assess_weak_extraction,
    extract_og_metadata,
    normalize_whitespace,
    prefer_extraction_candidate,
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
    archived_markdown = ""
    raw_capture_kind = ""
    summarize_metadata: dict = {}

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

    current_quality = score_extraction_quality(
        extracted,
        has_title=bool(item.title or og_meta.get("og_title") or og_meta.get("page_title")),
        is_metadata_only=(method == "metadata_only"),
    )
    weakness = assess_weak_extraction(
        extracted,
        title=item.title or og_meta.get("og_title") or og_meta.get("page_title") or "",
        extraction_quality=current_quality.value,
        source_kind="generic",
        min_chars=settings.summarize_weak_text_min_chars,
        min_paragraphs=settings.summarize_weak_paragraph_min_count,
        x_snippet_max_chars=settings.summarize_weak_x_snippet_max_chars,
    )

    if (
        weakness.is_weak
        and getattr(settings, "summarize_use_for_generic_fallback", False)
        and summarize_is_available(settings)
    ):
        fallback_chain.append("summarize_cli")
        summarize_result = await summarize_extract_url(
            item.url,
            source_kind="generic",
            prefer_markdown=getattr(settings, "summarize_prefer_markdown", True),
            settings=settings,
        )
        if summarize_result.success:
            summarize_content = summarize_result_to_source_content(
                item,
                summarize_result,
                raw_capture_kind="summarize_generic_extract",
                fallback_chain=fallback_chain.copy(),
                notes_prefix="summarize fallback for generic extraction.",
            )
            if prefer_extraction_candidate(
                current_text=extracted,
                current_quality=current_quality.value,
                candidate_text=summarize_content.cleaned_text,
                candidate_quality=summarize_content.extraction_quality,
            ):
                extracted = summarize_content.cleaned_text
                archived_markdown = summarize_content.archived_markdown
                raw_capture_kind = summarize_content.raw_capture_kind
                method = summarize_content.extraction_method
                canonical = summarize_content.canonical_url or canonical
                summarize_metadata = {"summarize": summarize_content.raw_metadata}
                notes_parts.append(
                    "summarize improved weak generic extraction: "
                    + ", ".join(weakness.reasons)
                    + "."
                )
            else:
                notes_parts.append("summarize fallback did not improve generic extraction.")
        else:
            notes_parts.append(f"summarize fallback failed: {summarize_result.provider_notes}")

    if (
        assess_weak_extraction(
            extracted,
            title=item.title or og_meta.get("og_title") or og_meta.get("page_title") or "",
            extraction_quality=score_extraction_quality(
                extracted,
                has_title=bool(item.title or og_meta.get("og_title") or og_meta.get("page_title")),
                is_metadata_only=(method == "metadata_only"),
            ).value,
            source_kind="generic",
            min_chars=settings.summarize_weak_text_min_chars,
            min_paragraphs=settings.summarize_weak_paragraph_min_count,
            x_snippet_max_chars=settings.summarize_weak_x_snippet_max_chars,
        ).is_weak
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
                archived_markdown = ""
                raw_capture_kind = ""
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
        archived_markdown=archived_markdown,
        raw_capture_kind=raw_capture_kind,
        word_count=len(extracted.split()) if extracted else 0,
        extraction_quality=quality.value,
        extraction_method=method,
        extraction_fallback_chain=fallback_chain,
        extraction_notes=" ".join(notes_parts),
        raw_metadata={**og_meta, **summarize_metadata},
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
