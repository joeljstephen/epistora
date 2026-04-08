"""Content fetchers for different source types with logged dispatch."""

from __future__ import annotations

import logging
import time

from app.connectors.fetchers.article import fetch_article
from app.connectors.fetchers.generic import fetch_generic
from app.connectors.fetchers.pdf import fetch_pdf
from app.connectors.fetchers.x_thread import fetch_x_thread
from app.connectors.fetchers.youtube import fetch_youtube
from app.models.source import SourceContent, SourceItem, SourceType
from app.utils.http import UnsafeUrlError, assert_safe_http_url

logger = logging.getLogger(__name__)


async def fetch_content(item: SourceItem) -> SourceContent:
    """Route to the appropriate fetcher based on source type, with logging."""
    try:
        assert_safe_http_url(item.url)
    except UnsafeUrlError as exc:
        from app.utils.hashing import url_hash

        item.title = item.title or item.url
        return SourceContent(
            source=item,
            extraction_quality="failed",
            extraction_method="none",
            extraction_fallback_chain=["url_safety_check"],
            extraction_notes=str(exc),
            url_hash=url_hash(item.url),
        )

    if item.source_type == SourceType.GENERIC and any(
        tag.strip().lower() == "article" for tag in item.tags
    ):
        logger.info(
            "Promoting generic source to article extraction due to Raindrop tag: %s",
            item.url,
        )
        item.source_type = SourceType.ARTICLE

    fetchers = {
        SourceType.ARTICLE: fetch_article,
        SourceType.YOUTUBE: fetch_youtube,
        SourceType.X_THREAD: fetch_x_thread,
        SourceType.PDF: fetch_pdf,
        SourceType.GENERIC: fetch_generic,
    }
    fetcher = fetchers.get(item.source_type, fetch_generic)
    fetcher_name = fetcher.__name__

    logger.info(
        "Extraction started: type=%s url=%s fetcher=%s",
        item.source_type.value,
        item.url[:120],
        fetcher_name,
    )

    start = time.monotonic()
    try:
        result = await fetcher(item)
    except Exception as exc:
        elapsed = time.monotonic() - start
        logger.error(
            "Extraction crashed: fetcher=%s url=%s elapsed=%.1fs error=%s",
            fetcher_name, item.url[:120], elapsed, exc,
        )
        from app.utils.hashing import url_hash

        item.title = item.title or item.url
        return SourceContent(
            source=item,
            extraction_quality="failed",
            extraction_method="none",
            extraction_fallback_chain=[fetcher_name, "unhandled_exception"],
            extraction_notes=f"Fetcher {fetcher_name} raised {type(exc).__name__}: {exc}",
            url_hash=url_hash(item.url),
        )

    elapsed = time.monotonic() - start
    logger.info(
        "Extraction complete: type=%s quality=%s method=%s chain=%s elapsed=%.1fs url=%s",
        item.source_type.value,
        result.extraction_quality,
        result.extraction_method,
        result.extraction_fallback_chain,
        elapsed,
        item.url[:120],
    )

    result.source.title = result.source.title or item.title or item.url
    return result
