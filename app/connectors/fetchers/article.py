from __future__ import annotations

import httpx
import trafilatura

from app.models.source import SourceContent, SourceItem
from app.utils.hashing import content_hash, url_hash


async def fetch_article(item: SourceItem) -> SourceContent:
    """Extract readable article content using trafilatura."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(item.url)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        return SourceContent(
            source=item,
            raw_text="",
            cleaned_text="",
            extraction_quality="failed",
            extraction_notes=f"HTTP fetch failed: {e}",
            url_hash=url_hash(item.url),
        )

    extracted = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=True,
        output_format="txt",
    )

    metadata = trafilatura.extract(
        html,
        include_comments=False,
        output_format="xmltei",
    )

    raw_text = html[:50000]
    cleaned = extracted or ""
    author = ""
    published = ""

    if metadata:
        import re

        author_match = re.search(r"<author>([^<]+)</author>", metadata)
        if author_match:
            author = author_match.group(1)
        date_match = re.search(r"<date[^>]*>([^<]+)</date>", metadata)
        if date_match:
            published = date_match.group(1)

    quality = "good" if len(cleaned) > 200 else ("partial" if cleaned else "failed")
    notes = "" if quality == "good" else "Extraction yielded limited content."

    title = item.title
    if not title and cleaned:
        title = cleaned.split("\n")[0][:120]

    item.title = title or item.url

    return SourceContent(
        source=item,
        raw_text=raw_text,
        cleaned_text=cleaned,
        author=author,
        published_date=published,
        word_count=len(cleaned.split()) if cleaned else 0,
        extraction_quality=quality,
        extraction_notes=notes,
        content_hash=content_hash(cleaned) if cleaned else "",
        url_hash=url_hash(item.url),
    )
