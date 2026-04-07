from __future__ import annotations

from slugify import slugify as _slugify


def slugify(text: str, max_length: int = 80) -> str:
    return _slugify(text, max_length=max_length, word_boundary=True)


def note_id(source_type: str, slug: str) -> str:
    """Build a stable note identifier like 'article-my-great-post'."""
    return f"{source_type}-{slug}"
