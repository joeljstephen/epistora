"""Shared extraction helpers: quality scoring, URL canonicalization, text cleanup."""

from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

from app.models.source import ExtractionQuality


def score_extraction_quality(
    text: str,
    *,
    has_title: bool = False,
    is_metadata_only: bool = False,
    is_translated: bool = False,
    is_auto_caption: bool = False,
) -> ExtractionQuality:
    """Rate extraction quality based on heuristics."""
    if is_metadata_only or not text.strip():
        return ExtractionQuality.METADATA_ONLY

    word_count = len(text.split())
    paragraph_count = len([p for p in text.split("\n\n") if p.strip()])

    if word_count >= 200 and paragraph_count >= 2 and has_title:
        if is_translated or is_auto_caption:
            return ExtractionQuality.MOSTLY_FULL
        return ExtractionQuality.FULL

    if word_count >= 100:
        return ExtractionQuality.MOSTLY_FULL

    if word_count >= 20:
        return ExtractionQuality.PARTIAL

    return ExtractionQuality.METADATA_ONLY


def resolve_canonical_url(html: str, original_url: str) -> str:
    """Extract canonical URL from HTML <link rel=canonical> or og:url, fallback to original."""
    canonical_match = re.search(
        r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']', html, re.I
    )
    if canonical_match:
        return canonical_match.group(1)

    og_url_match = re.search(
        r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)["\']', html, re.I
    )
    if og_url_match:
        return og_url_match.group(1)

    return original_url


def normalize_whitespace(text: str) -> str:
    """Collapse excessive whitespace while preserving paragraph breaks."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_og_metadata(html: str) -> dict:
    """Pull Open Graph and basic meta tags from HTML."""
    meta: dict[str, str] = {}

    _prop = r"""<meta[^>]+property=["\']og:{prop}["\'][^>]+content=["\']([^"\']+)["\']"""
    _name = r"""<meta[^>]+name=["\']{name}["\'][^>]+content=["\']([^"\']+)["\']"""
    patterns = {
        "og_title": _prop.format(prop="title"),
        "og_description": _prop.format(prop="description"),
        "og_image": _prop.format(prop="image"),
        "og_url": _prop.format(prop="url"),
        "og_type": _prop.format(prop="type"),
        "og_site_name": _prop.format(prop="site_name"),
        "description": _name.format(name="description"),
        "author": _name.format(name="author"),
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, html, re.I)
        if match:
            meta[key] = match.group(1)

    title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
    if title_match:
        meta["page_title"] = title_match.group(1).strip()

    return meta


def truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    """Truncate text to max_chars at a word boundary. Returns (text, was_truncated)."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text, False
    truncated = text[:max_chars].rsplit(" ", 1)[0]
    return truncated, True


def clean_url(url: str) -> str:
    """Normalize a URL for consistency."""
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((parsed.scheme.lower(), host, path, parsed.params, parsed.query, ""))
