"""PDF content extraction using PyMuPDF."""

from __future__ import annotations

import logging
import tempfile

import httpx

from app.models.source import ExtractionQuality, SourceContent, SourceItem
from app.utils.extraction import normalize_whitespace, score_extraction_quality
from app.utils.hashing import content_hash, url_hash
from app.utils.http import assert_safe_http_url

logger = logging.getLogger(__name__)


async def fetch_pdf(item: SourceItem) -> SourceContent:
    """Download a PDF and extract text using PyMuPDF."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
            resp = await client.get(item.url)
            resp.raise_for_status()
            response_url = (
                resp.url if isinstance(getattr(resp, "url", None), str | httpx.URL) else item.url
            )
            assert_safe_http_url(str(response_url))
            pdf_bytes = resp.content
    except Exception as e:
        return SourceContent(
            source=item,
            extraction_quality="failed",
            extraction_method="none",
            extraction_fallback_chain=["pdf_download_failed"],
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

            metadata = doc.metadata or {}
            doc.close()
            full_text = "\n\n".join(pages_text)
    except Exception as e:
        return SourceContent(
            source=item,
            raw_text=f"[Binary PDF — {len(pdf_bytes)} bytes]",
            extraction_quality="failed",
            extraction_method="pymupdf",
            extraction_fallback_chain=["pymupdf"],
            extraction_notes=f"PDF text extraction failed: {e}",
            url_hash=url_hash(item.url),
        )

    full_text = normalize_whitespace(full_text)
    has_title = bool(item.title or metadata.get("title"))
    quality = score_extraction_quality(full_text, has_title=has_title)

    if not item.title:
        item.title = metadata.get("title") or ""
    if not item.title and full_text:
        item.title = full_text.strip().split("\n")[0][:120]
    if not item.title:
        item.title = "Untitled PDF"

    author = metadata.get("author", "")
    raw_meta = {
        k: v for k, v in metadata.items() if v
    }
    raw_meta["page_count"] = len(pages_text)
    raw_meta["byte_size"] = len(pdf_bytes)

    return SourceContent(
        source=item,
        raw_text=full_text,
        cleaned_text=full_text,
        author=author,
        word_count=len(full_text.split()),
        extraction_quality=quality.value,
        extraction_method="pymupdf",
        extraction_fallback_chain=["pymupdf"],
        extraction_notes=(
            "" if quality != ExtractionQuality.METADATA_ONLY
            else "PDF yielded very little text; may be scanned/image-based."
        ),
        raw_metadata=raw_meta,
        canonical_url=item.url,
        content_hash=content_hash(full_text) if full_text else "",
        url_hash=url_hash(item.url),
    )
