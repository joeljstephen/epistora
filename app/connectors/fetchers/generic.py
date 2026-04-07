from __future__ import annotations

import httpx
import trafilatura

from app.models.source import SourceContent, SourceItem
from app.utils.hashing import content_hash, url_hash


async def fetch_generic(item: SourceItem) -> SourceContent:
    """Fallback fetcher: try readable text extraction from any URL."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(item.url)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        return SourceContent(
            source=item,
            extraction_quality="failed",
            extraction_notes=f"HTTP fetch failed: {e}",
            url_hash=url_hash(item.url),
        )

    extracted = trafilatura.extract(html, include_comments=False, include_tables=True) or ""
    quality = "good" if len(extracted) > 200 else ("partial" if extracted else "failed")

    if not item.title:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        item.title = (title_tag.get_text(strip=True) if title_tag else "") or item.url

    notes = ""
    if quality != "good":
        notes = (
            "Generic fallback extraction was used. "
            "Content quality may be limited for this page type."
        )

    return SourceContent(
        source=item,
        raw_text=html[:50000],
        cleaned_text=extracted,
        word_count=len(extracted.split()) if extracted else 0,
        extraction_quality=quality,
        extraction_notes=notes,
        content_hash=content_hash(extracted) if extracted else "",
        url_hash=url_hash(item.url),
    )
