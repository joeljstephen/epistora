from __future__ import annotations

import hashlib
from urllib.parse import urlparse, urlunparse


def normalize_url(url: str) -> str:
    """Canonicalize a URL for dedup: lowercase host, strip fragment & trailing slash."""
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((parsed.scheme.lower(), host, path, parsed.params, parsed.query, ""))


def url_hash(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode()).hexdigest()[:16]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]
