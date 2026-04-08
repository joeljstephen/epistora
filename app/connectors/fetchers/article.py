"""Article content extraction with multi-tier fallback chain.

Fallback order:
1. Trafilatura (primary)
2. readability-lxml (if configured and trafilatura weak)
3. Browser-rendered + trafilatura/readability (optional, config-controlled)
4. Metadata-only (OG tags, title, description)
"""

from __future__ import annotations

import logging
import re

import httpx
import trafilatura

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

logger = logging.getLogger(__name__)


async def fetch_article(item: SourceItem) -> SourceContent:
    """Extract readable article content with full fallback chain."""
    settings = get_settings()
    timeout = settings.article_fetch_timeout_seconds
    fallback_chain: list[str] = []
    notes_parts: list[str] = []

    html = await _fetch_html(item.url, timeout=timeout)
    if html is None:
        return _failed_result(item, "Unable to fetch source HTML.")

    og_meta = extract_og_metadata(html)
    canonical = resolve_canonical_url(html, item.url)

    cleaned, markdown_body, author, published, method = _coerce_trafilatura_result(
        _try_trafilatura(html)
    )
    fallback_chain.append("trafilatura")

    if len(cleaned) < 200 and settings.article_use_readability_fallback:
        readability_text, readability_title = extract_with_readability(html)
        fallback_chain.append("readability")
        if len(readability_text) > len(cleaned):
            notes_parts.append(
                f"Trafilatura yielded {len(cleaned)} chars; "
                f"readability improved to {len(readability_text)}."
            )
            cleaned = readability_text
            markdown_body = _plain_text_to_markdown(readability_text)
            method = "readability"
            if not item.title and readability_title:
                item.title = readability_title

    if (
        len(cleaned) < 200
        and settings.article_use_browser_fallback
        and settings.browser_fallback_enabled
        and is_browser_available()
    ):
        rendered_html = await fetch_rendered_html(
            item.url, timeout_ms=settings.browser_fallback_timeout_seconds * 1000
        )
        if rendered_html:
            fallback_chain.append("browser_rendered")
            browser_text, browser_markdown, browser_method = _extract_best_text(
                rendered_html,
                allow_readability=settings.article_use_readability_fallback,
            )
            if len(browser_text) > len(cleaned):
                notes_parts.append(
                    f"Browser rendering recovered {len(browser_text)} chars "
                    f"vs {len(cleaned)} from static."
                )
                cleaned = browser_text
                markdown_body = browser_markdown
                method = f"browser_rendered+{browser_method}"

    if not cleaned:
        fallback_chain.append("metadata_only")
        method = "metadata_only"
        cleaned = og_meta.get("og_description") or og_meta.get("description") or ""
        markdown_body = _plain_text_to_markdown(cleaned)
        notes_parts.append("All extractors failed; using metadata-only content.")

    cleaned = normalize_whitespace(cleaned)
    if not author:
        author = og_meta.get("author", "")
    if not item.title:
        item.title = og_meta.get("og_title") or og_meta.get("page_title") or ""
    if not item.title and cleaned:
        item.title = cleaned.split("\n")[0][:120]
    item.title = item.title or item.url

    quality = score_extraction_quality(
        cleaned,
        has_title=bool(item.title),
        is_metadata_only=(method == "metadata_only"),
    )

    archived_markdown = _build_article_archive_markdown(
        title=item.title,
        source_url=item.url,
        canonical_url=canonical,
        author=author,
        published=published,
        extraction_method=method,
        extraction_quality=quality.value,
        body_markdown=markdown_body,
        cleaned_text=cleaned,
    )

    raw_metadata = {"article_archive_available": bool(archived_markdown), **og_meta}

    return SourceContent(
        source=item,
        raw_text=html[:50000],
        cleaned_text=cleaned,
        archived_markdown=archived_markdown,
        raw_capture_kind="readable_article_markdown",
        author=author,
        published_date=published,
        word_count=len(cleaned.split()) if cleaned else 0,
        extraction_quality=quality.value,
        extraction_method=method,
        extraction_fallback_chain=fallback_chain,
        extraction_notes=" ".join(notes_parts),
        raw_metadata=raw_metadata,
        canonical_url=canonical,
        content_hash=content_hash(cleaned) if cleaned else "",
        url_hash=url_hash(item.url),
    )


async def _fetch_html(url: str, *, timeout: int = 30) -> str | None:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
    except Exception as exc:
        logger.warning("HTTP fetch failed for %s: %s", url, exc)
        return None


def _try_trafilatura(html: str) -> tuple[str, str, str, str, str]:
    """Run trafilatura and return (text, markdown, author, date, method)."""
    extracted = trafilatura.extract(
        html, include_comments=False, include_tables=True, output_format="txt"
    ) or ""
    markdown = trafilatura.extract(
        html, include_comments=False, include_tables=True, output_format="markdown"
    ) or ""

    author = ""
    published = ""
    tei = trafilatura.extract(html, include_comments=False, output_format="xmltei")
    if tei:
        author_match = re.search(r"<author>([^<]+)</author>", tei)
        if author_match:
            author = author_match.group(1)
        date_match = re.search(r"<date[^>]*>([^<]+)</date>", tei)
        if date_match:
            published = date_match.group(1)

    return extracted, markdown, author, published, "trafilatura"


def _coerce_trafilatura_result(result: tuple) -> tuple[str, str, str, str, str]:
    if len(result) == 5:
        return result  # type: ignore[return-value]
    if len(result) == 4:
        text, author, published, method = result
        return text, "", author, published, method
    raise ValueError(f"Unexpected trafilatura result shape: {len(result)}")


def _extract_best_text(html: str, *, allow_readability: bool) -> tuple[str, str, str]:
    """Extract readable text from HTML, preferring trafilatura then readability."""
    trafilatura_text, trafilatura_markdown, _, _, _ = _coerce_trafilatura_result(
        _try_trafilatura(html)
    )
    if not allow_readability:
        return trafilatura_text, trafilatura_markdown, "trafilatura"

    readability_text, _ = extract_with_readability(html)

    if len(readability_text) > len(trafilatura_text):
        return readability_text, _plain_text_to_markdown(readability_text), "readability"

    return trafilatura_text, trafilatura_markdown, "trafilatura"


def _plain_text_to_markdown(text: str) -> str:
    text = normalize_whitespace(text)
    if not text:
        return ""

    blocks: list[str] = []
    for raw_block in re.split(r"\n\s*\n+", text):
        block = " ".join(line.strip() for line in raw_block.splitlines() if line.strip())
        if not block:
            continue
        if len(block.split()) > 140:
            blocks.extend(_chunk_words(block, chunk_size=95))
            continue
        blocks.append(block)

    return "\n\n".join(blocks)


def _chunk_words(text: str, *, chunk_size: int) -> list[str]:
    words = text.split()
    chunks: list[str] = []
    for idx in range(0, len(words), chunk_size):
        chunks.append(" ".join(words[idx : idx + chunk_size]))
    return chunks


def _strip_duplicate_heading(markdown_body: str, title: str) -> str:
    lines = markdown_body.strip().splitlines()
    if not lines:
        return ""

    first = lines[0].lstrip("# ").strip()
    if first.lower() == title.strip().lower():
        return "\n".join(lines[1:]).strip()
    return markdown_body.strip()


def _build_article_archive_markdown(
    *,
    title: str,
    source_url: str,
    canonical_url: str,
    author: str,
    published: str,
    extraction_method: str,
    extraction_quality: str,
    body_markdown: str,
    cleaned_text: str,
) -> str:
    article_body = _strip_duplicate_heading(body_markdown, title) or _plain_text_to_markdown(
        cleaned_text
    )

    meta_lines = [
        f"# {title}",
        "",
        f"> Source: {source_url}",
    ]
    if canonical_url and canonical_url != source_url:
        meta_lines.append(f"> Canonical: {canonical_url}")
    if author:
        meta_lines.append(f"> Author: {author}")
    if published:
        meta_lines.append(f"> Published: {published}")
    meta_lines.append(
        f"> Extraction: {extraction_method or 'unknown'} ({extraction_quality or 'unknown'})"
    )
    meta_lines.extend(["", "---", ""])

    if article_body:
        meta_lines.append(article_body.strip())
    else:
        meta_lines.append("_Readable article body could not be preserved beyond metadata._")

    return "\n".join(meta_lines).strip()


def _failed_result(item: SourceItem, reason: str) -> SourceContent:
    return SourceContent(
        source=item,
        raw_text="",
        cleaned_text="",
        archived_markdown="",
        raw_capture_kind="readable_article_markdown",
        extraction_quality="failed",
        extraction_method="none",
        extraction_fallback_chain=["failed"],
        extraction_notes=f"HTTP fetch failed: {reason}",
        url_hash=url_hash(item.url),
    )
