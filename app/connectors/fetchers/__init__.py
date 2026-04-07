"""Content fetchers for different source types."""

from __future__ import annotations

from app.connectors.fetchers.article import fetch_article
from app.connectors.fetchers.generic import fetch_generic
from app.connectors.fetchers.pdf import fetch_pdf
from app.connectors.fetchers.x_thread import fetch_x_thread
from app.connectors.fetchers.youtube import fetch_youtube
from app.models.source import SourceContent, SourceItem, SourceType


async def fetch_content(item: SourceItem) -> SourceContent:
    """Route to the appropriate fetcher based on source type."""
    fetchers = {
        SourceType.ARTICLE: fetch_article,
        SourceType.YOUTUBE: fetch_youtube,
        SourceType.X_THREAD: fetch_x_thread,
        SourceType.PDF: fetch_pdf,
        SourceType.GENERIC: fetch_generic,
    }
    fetcher = fetchers.get(item.source_type, fetch_generic)
    return await fetcher(item)
