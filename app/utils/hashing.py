from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "igshid",
    "ref",
}


def normalize_url(url: str) -> str:
    """Canonicalize a URL for lightweight dedup without remote fetches."""
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    scheme = parsed.scheme.lower()
    path = parsed.path.rstrip("/") or "/"
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS
        and not key.lower().startswith(TRACKING_QUERY_PREFIXES)
    ]

    if host in {"youtu.be", "www.youtu.be"} and path != "/":
        host = "www.youtube.com"
        video_id = path.strip("/").split("/")[0]
        path = "/watch"
        query_pairs = [("v", video_id)]
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        host = "www.youtube.com"
        if path == "/watch":
            video_id = next((value for key, value in query_pairs if key == "v"), "")
            query_pairs = [("v", video_id)] if video_id else []

    query = urlencode(query_pairs)
    return urlunparse((scheme, host, path, parsed.params, query, ""))


def url_hash(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode()).hexdigest()[:16]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]
