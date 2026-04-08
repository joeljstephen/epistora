"""Shared extraction helpers: quality scoring, URL canonicalization, text cleanup."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

from app.models.source import ExtractionQuality


@dataclass(slots=True)
class WeakExtractionAssessment:
    is_weak: bool
    reasons: list[str]


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


def quality_rank(quality: str | ExtractionQuality | None) -> int:
    value = quality.value if isinstance(quality, ExtractionQuality) else (quality or "")
    ranks = {
        ExtractionQuality.FAILED.value: 0,
        ExtractionQuality.METADATA_ONLY.value: 1,
        ExtractionQuality.PARTIAL.value: 2,
        ExtractionQuality.MOSTLY_FULL.value: 3,
        ExtractionQuality.FULL.value: 4,
    }
    return ranks.get(value, 0)


def assess_weak_extraction(
    text: str,
    *,
    title: str = "",
    extraction_quality: str = "",
    source_kind: str = "generic",
    min_chars: int = 400,
    min_paragraphs: int = 2,
    x_snippet_max_chars: int = 320,
) -> WeakExtractionAssessment:
    min_chars = _coerce_int(min_chars, 200)
    min_paragraphs = _coerce_int(min_paragraphs, 2)
    x_snippet_max_chars = _coerce_int(x_snippet_max_chars, 320)

    cleaned = normalize_whitespace(text)
    reasons: list[str] = []

    if extraction_quality in {
        ExtractionQuality.FAILED.value,
        ExtractionQuality.METADATA_ONLY.value,
    }:
        reasons.append(f"quality={extraction_quality or 'unknown'}")

    if not cleaned:
        reasons.append("empty_body")
        return WeakExtractionAssessment(is_weak=True, reasons=reasons)

    paragraphs = [p for p in re.split(r"\n\s*\n", cleaned) if p.strip()]
    if len(cleaned) < max(min_chars, 1):
        reasons.append(f"short_body<{min_chars}")
    if len(paragraphs) < max(min_paragraphs, 1) and len(cleaned) < (min_chars * 2):
        reasons.append(f"paragraphs<{min_paragraphs}")

    normalized_title = normalize_whitespace(title).lower()
    lowered = cleaned.lower()
    if normalized_title and (
        lowered == normalized_title
        or (lowered.startswith(normalized_title) and len(cleaned.split()) <= 20)
    ):
        reasons.append("title_only")

    trailing_window = cleaned[-160:]
    if re.search(
        r"(continue reading|read more|sign in to read|subscribe to continue)",
        trailing_window,
        re.I,
    ):
        reasons.append("truncated_teaser")
    if trailing_window.endswith(("...", "…")):
        reasons.append("truncated_tail")

    if source_kind == "x" and len(cleaned) <= max(x_snippet_max_chars, 1) and len(paragraphs) <= 1:
        reasons.append("x_preview_snippet")

    return WeakExtractionAssessment(is_weak=bool(reasons), reasons=reasons)


def prefer_extraction_candidate(
    *,
    current_text: str,
    current_quality: str,
    candidate_text: str,
    candidate_quality: str,
) -> bool:
    current_rank = quality_rank(current_quality)
    candidate_rank = quality_rank(candidate_quality)
    if candidate_rank != current_rank:
        return candidate_rank > current_rank
    return len(normalize_whitespace(candidate_text)) > len(normalize_whitespace(current_text))


def _coerce_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return default


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
