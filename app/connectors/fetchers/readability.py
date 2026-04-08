"""Readability-style article extraction fallback using readability-lxml."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_READABILITY_AVAILABLE: bool | None = None


def is_readability_available() -> bool:
    global _READABILITY_AVAILABLE
    if _READABILITY_AVAILABLE is None:
        try:
            from readability import Document  # noqa: F401

            _READABILITY_AVAILABLE = True
        except ImportError:
            _READABILITY_AVAILABLE = False
    return _READABILITY_AVAILABLE


def extract_with_readability(html: str) -> tuple[str, str]:
    """Extract article text using readability-lxml.

    Returns (cleaned_text, title). Falls back to empty strings on failure.
    """
    if not is_readability_available():
        return "", ""

    try:
        from readability import Document

        doc = Document(html)
        title = doc.short_title() or ""
        summary_html = doc.summary()
        text = _html_to_text(summary_html)
        return text, title
    except Exception as exc:
        logger.warning("Readability extraction failed: %s", exc)
        return "", ""


def _html_to_text(html: str) -> str:
    """Minimal HTML→plaintext using BeautifulSoup."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
    except Exception:
        return re.sub(r"<[^>]+>", " ", html).strip()
