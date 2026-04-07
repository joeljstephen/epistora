from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

from app.models.source import SourceContent, SourceItem
from app.utils.hashing import content_hash, url_hash


async def fetch_x_thread(item: SourceItem) -> SourceContent:
    """Best-effort extraction of X/Twitter post content.

    X does not provide a public API for unauthenticated tweet extraction.
    This fetcher attempts to get metadata via noembed and page scraping,
    but results may be incomplete. The note will clearly indicate the
    extraction quality.
    """
    extracted_text = ""
    author = ""
    quality = "partial"
    notes_parts: list[str] = []

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            noembed_resp = await client.get(
                "https://noembed.com/embed",
                params={"url": item.url},
            )
            if noembed_resp.status_code == 200:
                data = noembed_resp.json()
                author = data.get("author_name", "")
                if not item.title:
                    item.title = data.get("title", "") or data.get("author_name", "")
    except Exception:
        notes_parts.append("noembed metadata fetch failed.")

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            page = await client.get(item.url)
            if page.status_code == 200:
                soup = BeautifulSoup(page.text, "html.parser")
                og_desc = soup.find("meta", property="og:description")
                if og_desc and og_desc.get("content"):
                    extracted_text = og_desc["content"]
                    if not item.title:
                        og_title = soup.find("meta", property="og:title")
                        if og_title and og_title.get("content"):
                            item.title = og_title["content"]
    except Exception:
        notes_parts.append("Page scraping failed.")

    if not extracted_text:
        quality = "metadata_only"
        notes_parts.append(
            "X/Twitter content extraction is limited without API authentication. "
            "The post text may be incomplete or missing."
        )

    if not item.title:
        item.title = f"X Post – {item.url.split('/')[-1]}"

    raw_text = f"URL: {item.url}\nAuthor: {author}\n\n{extracted_text}"

    return SourceContent(
        source=item,
        raw_text=raw_text,
        cleaned_text=extracted_text,
        author=author,
        word_count=len(extracted_text.split()) if extracted_text else 0,
        extraction_quality=quality,
        extraction_notes=" ".join(notes_parts) if notes_parts else "",
        content_hash=content_hash(extracted_text) if extracted_text else "",
        url_hash=url_hash(item.url),
    )
