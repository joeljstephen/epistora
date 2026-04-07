"""Classify a URL into a SourceType."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from app.models.source import SourceType

_YOUTUBE_PATTERNS = [
    re.compile(r"(youtube\.com/watch\?v=)"),
    re.compile(r"(youtu\.be/)"),
    re.compile(r"(youtube\.com/embed/)"),
    re.compile(r"(youtube\.com/shorts/)"),
]

_X_PATTERNS = [
    re.compile(r"(twitter\.com/.+/status/)"),
    re.compile(r"(x\.com/.+/status/)"),
    re.compile(r"^https?://(www\.)?(twitter|x)\.com/"),
]


def classify_url(url: str) -> SourceType:
    """Determine source type from a URL."""
    lower = url.lower().strip()

    for pat in _YOUTUBE_PATTERNS:
        if pat.search(lower):
            return SourceType.YOUTUBE

    for pat in _X_PATTERNS:
        if pat.search(lower):
            return SourceType.X_THREAD

    parsed = urlparse(lower)
    path = parsed.path.lower()

    if path.endswith(".pdf"):
        return SourceType.PDF

    return SourceType.ARTICLE
