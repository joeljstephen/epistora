"""X/Twitter post and thread extraction with five-tier fallback.

Tier 1: Official X API (if bearer token configured)
Tier 2: fxtwitter / vxtwitter free mirror APIs
Tier 3: oEmbed / noembed
Tier 4: Direct page scrape / Open Graph
Tier 5: Optional browser-rendered fallback (if enabled)
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.config import get_settings
from app.connectors.fetchers.browser import fetch_rendered_html, is_browser_available
from app.connectors.fetchers.summarize_cli import (
    extract_url as summarize_extract_url,
)
from app.connectors.fetchers.summarize_cli import (
    is_available as summarize_is_available,
)
from app.connectors.fetchers.summarize_cli import (
    summarize_result_to_source_content,
)
from app.connectors.fetchers.x_api import (
    assemble_thread_text,
    fetch_post_via_api,
    fetch_thread_via_api,
)
from app.connectors.fetchers.x_mirrors import (
    fetch_via_fxtwitter,
    fetch_via_oembed,
    fetch_via_page_scrape,
    fetch_via_vxtwitter,
)
from app.models.source import SourceContent, SourceItem
from app.utils.extraction import (
    assess_weak_extraction,
    normalize_whitespace,
    prefer_extraction_candidate,
    score_extraction_quality,
)
from app.utils.hashing import content_hash, url_hash

logger = logging.getLogger(__name__)

_POST_ID_RE = re.compile(r"/status/(\d+)")


def _extract_post_id(url: str) -> str | None:
    m = _POST_ID_RE.search(url)
    return m.group(1) if m else None


async def fetch_x_thread(item: SourceItem) -> SourceContent:
    """Best-effort extraction of X/Twitter post/thread/article content."""
    settings = get_settings()
    fallback_chain: list[str] = []
    notes_parts: list[str] = []
    post_id = _extract_post_id(item.url)
    best_candidate: dict[str, Any] | None = None

    # --- Tier 1: Official X API ---
    if settings.x_api_enabled and settings.x_api_bearer_token and post_id:
        result = await _tier_official_api(
            post_id, settings.x_api_bearer_token, settings.x_api_timeout_seconds
        )
        fallback_chain.append("x_api")
        if result:
            best_candidate = _select_better_candidate(
                best_candidate,
                _make_candidate(
                    text=result.get("text", ""),
                    method="x_api",
                    author=result.get("author", ""),
                    title=result.get("title", ""),
                    metadata=result.get("metadata", {}),
                    note=result.get("note", ""),
                ),
            )
            if result.get("note"):
                notes_parts.append(result["note"])

    # --- Tier 2: Free mirror APIs ---
    if settings.x_mirror_enabled and not _candidate_is_good_enough(best_candidate, settings):
        result = await _tier_mirror_apis(item.url, settings.x_mirror_timeout_seconds)
        fallback_chain.append("mirror_apis")
        if result:
            article_text = result.get("article_text", "")
            article_title = result.get("article_title", "")
            main_text = result.get("text", "")

            is_article_link = bool(re.search(r"x\.com/i/article/\d+", main_text))
            if article_text and is_article_link:
                main_text = ""
            elif article_text:
                main_text = f"{main_text}\n\n--- X Article ---\n\n{article_text}"
            else:
                main_text = main_text

            combined_title = article_title if article_title else ""

            best_candidate = _select_better_candidate(
                best_candidate,
                _make_candidate(
                    text=article_text if (article_text and is_article_link) else main_text,
                    method=result.get("source", "mirror"),
                    author=result.get("author", ""),
                    title=combined_title,
                    metadata=result.get("metadata", {}),
                    note=result.get("note", ""),
                ),
            )
            if result.get("note"):
                notes_parts.append(result["note"])

    # --- Tier 3: oEmbed / noembed ---
    if settings.x_oembed_enabled and not _candidate_is_good_enough(best_candidate, settings):
        result = await _tier_oembed(item.url, settings.x_mirror_timeout_seconds)
        fallback_chain.append("oembed")
        if result:
            best_candidate = _select_better_candidate(
                best_candidate,
                _make_candidate(
                    text=result.get("text", ""),
                    method=result.get("source", "oembed"),
                    author=result.get("author", ""),
                    note=result.get("note", ""),
                ),
            )
            if result.get("note"):
                notes_parts.append(result["note"])

    # --- Tier 4: summarize fallback ---
    if (
        getattr(settings, "summarize_use_for_x_fallback", False)
        and not _candidate_is_good_enough(best_candidate, settings)
        and summarize_is_available(settings)
    ):
        fallback_chain.append("summarize_cli")
        summarize_result = await summarize_extract_url(
            item.url,
            source_kind="x",
            prefer_markdown=getattr(settings, "summarize_prefer_markdown", True),
            settings=settings,
        )
        if summarize_result.success:
            summarize_content = summarize_result_to_source_content(
                item,
                summarize_result,
                raw_capture_kind="summarize_x_extract",
                fallback_chain=fallback_chain.copy(),
                notes_prefix="summarize fallback for X extraction.",
            )
            summarize_candidate = _make_candidate(
                text=summarize_content.cleaned_text,
                method=summarize_content.extraction_method,
                author=summarize_content.author,
                title=summarize_content.source.title,
                metadata={"summarize": summarize_content.raw_metadata},
                note=summarize_content.extraction_notes,
                raw_capture_kind=summarize_content.raw_capture_kind,
                canonical_url=summarize_content.canonical_url,
            )
            if _select_better_candidate(best_candidate, summarize_candidate) == summarize_candidate:
                best_candidate = summarize_candidate
                notes_parts.append("summarize improved the best available X extraction.")
            else:
                notes_parts.append("summarize fallback did not improve the best X extraction.")
        else:
            notes_parts.append(f"summarize fallback failed: {summarize_result.provider_notes}")

    # --- Tier 5: Page scrape / OG fallback ---
    if not _candidate_is_good_enough(best_candidate, settings):
        result = await _tier_page_scrape(item.url, settings.x_mirror_timeout_seconds)
        fallback_chain.append("page_scrape")
        if result:
            best_candidate = _select_better_candidate(
                best_candidate,
                _make_candidate(
                    text=result.get("text", ""),
                    method="page_scrape",
                    title=result.get("title", ""),
                ),
            )

    # --- Tier 6: Browser fallback ---
    if (
        not _candidate_is_good_enough(best_candidate, settings)
        and settings.browser_fallback_enabled
        and is_browser_available()
    ):
        rendered = await fetch_rendered_html(
            item.url, timeout_ms=settings.browser_fallback_timeout_seconds * 1000
        )
        fallback_chain.append("browser_rendered")
        if rendered:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(rendered, "html.parser")
            og_desc = soup.find("meta", property="og:description")
            if og_desc and og_desc.get("content"):
                best_candidate = _select_better_candidate(
                    best_candidate,
                    _make_candidate(
                        text=og_desc["content"],
                        method="browser_rendered",
                    ),
                )

    # --- Finalize ---
    if not best_candidate or not normalize_whitespace(best_candidate.get("text", "")):
        fallback_chain.append("metadata_only")
        notes_parts.append(
            "All X extraction tiers failed; only URL and any available metadata captured."
        )
        best_candidate = _make_candidate(text="", method="metadata_only")

    extracted_text = normalize_whitespace(best_candidate.get("text", ""))
    author = str(best_candidate.get("author", "") or "")
    method = str(best_candidate.get("method", "") or "metadata_only")
    raw_metadata = dict(best_candidate.get("metadata", {}) or {})

    if not item.title:
        if best_candidate.get("title"):
            item.title = str(best_candidate["title"])
        elif author:
            item.title = f"X Post by {author}"
        elif post_id:
            item.title = f"X Post {post_id}"
        else:
            item.title = f"X Post – {item.url.split('/')[-1]}"

    quality = score_extraction_quality(
        extracted_text,
        has_title=bool(item.title),
        is_metadata_only=(method == "metadata_only"),
    )

    raw_text = f"URL: {item.url}\nAuthor: {author}\n\n{extracted_text}"

    return SourceContent(
        source=item,
        raw_text=raw_text,
        cleaned_text=extracted_text,
        raw_capture_kind=str(best_candidate.get("raw_capture_kind", "") or ""),
        author=author,
        word_count=len(extracted_text.split()) if extracted_text else 0,
        extraction_quality=quality.value,
        extraction_method=method,
        extraction_fallback_chain=fallback_chain,
        extraction_notes=" ".join(notes_parts),
        raw_metadata=raw_metadata,
        canonical_url=str(best_candidate.get("canonical_url", "") or item.url),
        content_hash=content_hash(extracted_text) if extracted_text else "",
        url_hash=url_hash(item.url),
    )


def _make_candidate(
    *,
    text: str,
    method: str,
    author: str = "",
    title: str = "",
    metadata: dict[str, Any] | None = None,
    note: str = "",
    raw_capture_kind: str = "",
    canonical_url: str = "",
) -> dict[str, Any]:
    cleaned = normalize_whitespace(text)
    quality = score_extraction_quality(
        cleaned,
        has_title=bool(title),
        is_metadata_only=(method == "metadata_only"),
    ).value
    return {
        "text": cleaned,
        "method": method,
        "author": author,
        "title": title,
        "metadata": metadata or {},
        "note": note,
        "raw_capture_kind": raw_capture_kind,
        "canonical_url": canonical_url,
        "quality": quality,
    }


def _select_better_candidate(
    current: dict[str, Any] | None,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    if current is None:
        return candidate
    if prefer_extraction_candidate(
        current_text=str(current.get("text", "")),
        current_quality=str(current.get("quality", "")),
        candidate_text=str(candidate.get("text", "")),
        candidate_quality=str(candidate.get("quality", "")),
    ):
        return candidate
    return current


def _candidate_is_good_enough(candidate: dict[str, Any] | None, settings: Any) -> bool:
    if not candidate:
        return False
    weakness = assess_weak_extraction(
        str(candidate.get("text", "")),
        title=str(candidate.get("title", "")),
        extraction_quality=str(candidate.get("quality", "")),
        source_kind="x",
        min_chars=settings.summarize_weak_text_min_chars,
        min_paragraphs=settings.summarize_weak_paragraph_min_count,
        x_snippet_max_chars=settings.summarize_weak_x_snippet_max_chars,
    )
    return not weakness.is_weak


# ---------------------------------------------------------------------------
# Tier implementations
# ---------------------------------------------------------------------------


async def _tier_official_api(post_id: str, bearer_token: str, timeout: int) -> dict | None:
    """Tier 1: Official X API extraction."""
    thread = await fetch_thread_via_api(post_id, bearer_token, timeout=timeout)
    if not thread:
        single = await fetch_post_via_api(post_id, bearer_token, timeout=timeout)
        if not single:
            return None
        thread = [single]

    text = assemble_thread_text(thread)
    first = thread[0]
    author = first.get("author_name") or first.get("username", "")
    title = f"@{first.get('username', '')} — {text[:80]}..." if text else ""

    note = ""
    if len(thread) > 1:
        note = f"Thread with {len(thread)} posts reconstructed via X API."
    else:
        note = "Single post fetched via X API."

    metadata = {
        "post_id": post_id,
        "username": first.get("username", ""),
        "created_at": first.get("created_at", ""),
        "thread_length": len(thread),
        "metrics": first.get("metrics", {}),
    }

    return {"text": text, "author": author, "title": title, "note": note, "metadata": metadata}


async def _tier_mirror_apis(url: str, timeout: int) -> dict | None:
    """Tier 2: fxtwitter then vxtwitter."""
    fx = await fetch_via_fxtwitter(url, timeout=timeout)
    if fx:
        text = fx.get("text", "")
        article_text = fx.get("article_text", "")
        if article_text:
            text = f"{text}\n\n--- X Article ---\n\n{article_text}"

        note_parts = ["Extracted via fxtwitter."]
        if fx.get("is_thread"):
            note_parts.append("Thread content included.")
        if fx.get("has_article"):
            note_parts.append("Linked X article expanded.")

        return {
            "text": text,
            "article_text": fx.get("article_text", ""),
            "article_title": fx.get("article_title", ""),
            "author": fx.get("author_name") or fx.get("username", ""),
            "source": "fxtwitter",
            "note": " ".join(note_parts),
            "metadata": {
                "username": fx.get("username", ""),
                "likes": fx.get("likes", 0),
                "retweets": fx.get("retweets", 0),
                "source_api": "fxtwitter",
            },
        }

    vx = await fetch_via_vxtwitter(url, timeout=timeout)
    if vx:
        return {
            "text": vx.get("text", ""),
            "article_text": vx.get("article_text", ""),
            "article_title": vx.get("article_title", ""),
            "author": vx.get("author_name") or vx.get("username", ""),
            "source": "vxtwitter",
            "note": "Extracted via vxtwitter.",
            "metadata": {
                "username": vx.get("username", ""),
                "likes": vx.get("likes", 0),
                "retweets": vx.get("retweets", 0),
                "source_api": "vxtwitter",
            },
        }

    return None


async def _tier_oembed(url: str, timeout: int) -> dict | None:
    """Tier 3: oEmbed / noembed."""
    result = await fetch_via_oembed(url, timeout=timeout)
    if not result:
        return None
    return {
        "text": result.get("text", ""),
        "author": result.get("author_name", ""),
        "source": f"oembed_{result.get('source', 'unknown')}",
        "note": f"Extracted via oEmbed ({result.get('source', 'unknown')}).",
    }


async def _tier_page_scrape(url: str, timeout: int) -> dict | None:
    """Tier 4: Direct page scrape."""
    return await fetch_via_page_scrape(url, timeout=timeout)
