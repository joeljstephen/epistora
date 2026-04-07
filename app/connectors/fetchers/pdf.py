from __future__ import annotations

import tempfile

import httpx

from app.models.source import SourceContent, SourceItem
from app.utils.hashing import content_hash, url_hash


async def fetch_pdf(item: SourceItem) -> SourceContent:
    """Download a PDF and extract text using PyMuPDF."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
            resp = await client.get(item.url)
            resp.raise_for_status()
            pdf_bytes = resp.content
    except Exception as e:
        return SourceContent(
            source=item,
            extraction_quality="failed",
            extraction_notes=f"PDF download failed: {e}",
            url_hash=url_hash(item.url),
        )

    try:
        import pymupdf

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
            tmp.write(pdf_bytes)
            tmp.flush()
            doc = pymupdf.open(tmp.name)
            pages_text = []
            for page in doc:
                pages_text.append(page.get_text())
            doc.close()
            full_text = "\n\n".join(pages_text)
    except Exception as e:
        return SourceContent(
            source=item,
            raw_text=f"[Binary PDF — {len(pdf_bytes)} bytes]",
            extraction_quality="failed",
            extraction_notes=f"PDF text extraction failed: {e}",
            url_hash=url_hash(item.url),
        )

    quality = "good" if len(full_text) > 100 else "partial"
    if not item.title:
        first_line = full_text.strip().split("\n")[0][:120] if full_text else "Untitled PDF"
        item.title = first_line

    return SourceContent(
        source=item,
        raw_text=full_text,
        cleaned_text=full_text,
        word_count=len(full_text.split()),
        extraction_quality=quality,
        extraction_notes="" if quality == "good" else "PDF extraction yielded limited text.",
        content_hash=content_hash(full_text) if full_text else "",
        url_hash=url_hash(item.url),
    )
