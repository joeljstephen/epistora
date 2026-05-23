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
from app.connectors.fetchers.readable import (
    ReadableExtractionDraft,
    apply_metadata_only_fallback,
    apply_summarize_candidate,
    assess_draft_weakness,
    build_source_content,
)
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
    extract_og_metadata,
    resolve_canonical_url,
)
from app.utils.hashing import url_hash
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
    draft = ReadableExtractionDraft(canonical_url=canonical)

    extracted = trafilatura.extract(html, include_comments=False, include_tables=True) or ""
    draft.text = extracted
    draft.method = "trafilatura"
    draft.fallback_chain = fallback_chain
    draft.notes = notes_parts
    draft.fallback_chain.append("trafilatura")

    if len(draft.text) < 200:
        readability_text, readability_title = extract_with_readability(html)
        draft.fallback_chain.append("readability")
        if len(readability_text) > len(draft.text):
            draft.text = readability_text
            draft.method = "readability"
            if readability_title and not item.title:
                item.title = readability_title
            draft.notes.append("Readability fallback improved extraction.")

    title_hint = item.title or og_meta.get("og_title") or og_meta.get("page_title") or ""
    weakness = assess_draft_weakness(
        draft,
        title=item.title or og_meta.get("og_title") or og_meta.get("page_title") or "",
        source_kind="generic",
        settings=settings,
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
            apply_summarize_candidate(
                draft,
                summarize_content=summarize_content,
                weakness=weakness,
                improved_note="summarize improved weak generic extraction",
                not_improved_note="summarize fallback did not improve generic extraction.",
            )
        else:
            draft.notes.append(f"summarize fallback failed: {summarize_result.provider_notes}")

    if (
        assess_draft_weakness(
            draft,
            title=title_hint,
            source_kind="generic",
            settings=settings,
        ).is_weak
        and settings.browser_fallback_enabled
        and is_browser_available()
    ):
        rendered = await fetch_rendered_html(
            item.url, timeout_ms=settings.browser_fallback_timeout_seconds * 1000
        )
        draft.fallback_chain.append("browser_rendered")
        if rendered:
            browser_text, browser_method = _extract_best_text(rendered)
            if len(browser_text) > len(draft.text):
                draft.text = browser_text
                draft.method = f"browser_rendered+{browser_method}"
                draft.markdown = ""
                draft.raw_capture_kind = ""
                draft.notes.append("Browser rendering improved extraction.")

    if not draft.text:
        apply_metadata_only_fallback(
            draft,
            text=og_meta.get("og_description") or og_meta.get("description") or "",
            note="All extractors failed; generic metadata-only fallback.",
        )

    if not item.title:
        item.title = og_meta.get("og_title") or og_meta.get("page_title") or ""
    if not item.title:
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        item.title = (title_tag.get_text(strip=True) if title_tag else "") or item.url

    draft.raw_metadata = {**og_meta, **draft.raw_metadata}

    return build_source_content(
        item=item,
        raw_text=html[:50000],
        draft=draft,
        title=item.title,
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
