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

_ARTICLE_HOST_HINTS = (
    "blog.",
    "news.",
    "magazine.",
    "journal.",
    "medium.com",
    "substack.com",
)

_ARTICLE_PATH_HINTS = (
    "/article/",
    "/articles/",
    "/blog/",
    "/blogs/",
    "/post/",
    "/posts/",
    "/news/",
    "/essay/",
    "/essays/",
    "/p/",
)


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
    host = parsed.hostname or ""
    path = parsed.path.lower()

    if path.endswith(".pdf"):
        return SourceType.PDF

    if _looks_like_article(host, path):
        return SourceType.ARTICLE

    return SourceType.GENERIC


def _looks_like_article(host: str, path: str) -> bool:
    if not path or path == "/":
        return False

    if any(hint in host for hint in _ARTICLE_HOST_HINTS):
        return True

    if any(hint in path for hint in _ARTICLE_PATH_HINTS):
        return True

    if re.search(r"/\d{4}/\d{2}/\d{2}/", path):
        return True

    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False

    leaf = segments[-1]
    slug_tokens = [token for token in re.split(r"[-_]", leaf) if token]
    if len(slug_tokens) >= 3:
        return True

    return len(leaf) >= 25 and ("-" in leaf or "_" in leaf)
