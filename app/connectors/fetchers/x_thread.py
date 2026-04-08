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

from app.config import get_settings
from app.connectors.fetchers.browser import fetch_rendered_html, is_browser_available
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
from app.utils.extraction import normalize_whitespace, score_extraction_quality
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
    extracted_text = ""
    author = ""
    method = ""
    raw_metadata: dict = {}
    post_id = _extract_post_id(item.url)

    # --- Tier 1: Official X API ---
    if settings.x_api_enabled and settings.x_api_bearer_token and post_id:
        result = await _tier_official_api(
            post_id, settings.x_api_bearer_token, settings.x_api_timeout_seconds
        )
        fallback_chain.append("x_api")
        if result:
            extracted_text = result["text"]
            author = result.get("author", "")
            method = "x_api"
            raw_metadata = result.get("metadata", {})
            if not item.title and result.get("title"):
                item.title = result["title"]
            if result.get("note"):
                notes_parts.append(result["note"])

    # --- Tier 2: Free mirror APIs ---
    if not extracted_text and settings.x_mirror_enabled:
        result = await _tier_mirror_apis(item.url, settings.x_mirror_timeout_seconds)
        fallback_chain.append("mirror_apis")
        if result:
            extracted_text = result["text"]
            author = result.get("author", "") or author
            method = result.get("source", "mirror")
            raw_metadata.update(result.get("metadata", {}))
            if result.get("note"):
                notes_parts.append(result["note"])

    # --- Tier 3: oEmbed / noembed ---
    if not extracted_text and settings.x_oembed_enabled:
        result = await _tier_oembed(item.url, settings.x_mirror_timeout_seconds)
        fallback_chain.append("oembed")
        if result:
            extracted_text = result["text"]
            author = result.get("author", "") or author
            method = result.get("source", "oembed")
            if result.get("note"):
                notes_parts.append(result["note"])

    # --- Tier 4: Page scrape / OG fallback ---
    if not extracted_text:
        result = await _tier_page_scrape(item.url, settings.x_mirror_timeout_seconds)
        fallback_chain.append("page_scrape")
        if result:
            extracted_text = result.get("text", "")
            method = "page_scrape"
            if result.get("title") and not item.title:
                item.title = result["title"]

    # --- Tier 5: Browser fallback ---
    if (
        not extracted_text
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
                extracted_text = og_desc["content"]
                method = "browser_rendered"

    # --- Finalize ---
    if not extracted_text:
        fallback_chain.append("metadata_only")
        method = "metadata_only"
        notes_parts.append(
            "All X extraction tiers failed; only URL and any available metadata captured."
        )

    extracted_text = normalize_whitespace(extracted_text)

    if not item.title:
        if author:
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
        author=author,
        word_count=len(extracted_text.split()) if extracted_text else 0,
        extraction_quality=quality.value,
        extraction_method=method,
        extraction_fallback_chain=fallback_chain,
        extraction_notes=" ".join(notes_parts),
        raw_metadata=raw_metadata,
        canonical_url=item.url,
        content_hash=content_hash(extracted_text) if extracted_text else "",
        url_hash=url_hash(item.url),
    )


# ---------------------------------------------------------------------------
# Tier implementations
# ---------------------------------------------------------------------------


async def _tier_official_api(
    post_id: str, bearer_token: str, timeout: int
) -> dict | None:
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
