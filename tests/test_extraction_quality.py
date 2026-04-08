"""Tests for extraction quality scoring and utility functions."""

from __future__ import annotations

from app.models.source import ExtractionQuality
from app.utils.extraction import (
    extract_og_metadata,
    normalize_whitespace,
    resolve_canonical_url,
    score_extraction_quality,
    truncate_text,
)


class TestScoreExtractionQuality:
    def test_empty_text_is_metadata_only(self):
        assert score_extraction_quality("") == ExtractionQuality.METADATA_ONLY

    def test_metadata_only_flag(self):
        assert (
            score_extraction_quality("some text", is_metadata_only=True)
            == ExtractionQuality.METADATA_ONLY
        )

    def test_full_quality(self):
        text = "Word " * 250 + "\n\nSecond paragraph " * 20 + "\n\nThird paragraph."
        assert score_extraction_quality(text, has_title=True) == ExtractionQuality.FULL

    def test_mostly_full_for_auto_caption(self):
        text = "Word " * 250 + "\n\nSecond paragraph " * 20
        assert (
            score_extraction_quality(text, has_title=True, is_auto_caption=True)
            == ExtractionQuality.MOSTLY_FULL
        )

    def test_mostly_full_for_medium_text(self):
        text = "Word " * 120
        assert score_extraction_quality(text) == ExtractionQuality.MOSTLY_FULL

    def test_partial_for_short_text(self):
        text = "Word " * 30
        assert score_extraction_quality(text) == ExtractionQuality.PARTIAL

    def test_metadata_only_for_very_short(self):
        text = "Hello"
        assert score_extraction_quality(text) == ExtractionQuality.METADATA_ONLY


class TestResolveCanonicalUrl:
    def test_canonical_link(self):
        html = '<link rel="canonical" href="https://example.com/canonical">'
        assert resolve_canonical_url(html, "https://example.com/page") == "https://example.com/canonical"

    def test_og_url_fallback(self):
        html = '<meta property="og:url" content="https://example.com/og">'
        assert resolve_canonical_url(html, "https://example.com/page") == "https://example.com/og"

    def test_original_fallback(self):
        html = "<html><body>no meta</body></html>"
        assert resolve_canonical_url(html, "https://example.com/page") == "https://example.com/page"


class TestNormalizeWhitespace:
    def test_collapse_spaces(self):
        assert normalize_whitespace("hello   world") == "hello world"

    def test_collapse_newlines(self):
        assert normalize_whitespace("a\n\n\n\n\nb") == "a\n\nb"

    def test_strip(self):
        assert normalize_whitespace("  hello  ") == "hello"


class TestExtractOgMetadata:
    def test_extracts_og_tags(self):
        html = """
        <html><head>
        <title>Page Title</title>
        <meta property="og:title" content="OG Title">
        <meta property="og:description" content="OG Desc">
        <meta name="author" content="Author Name">
        </head></html>
        """
        meta = extract_og_metadata(html)
        assert meta["og_title"] == "OG Title"
        assert meta["og_description"] == "OG Desc"
        assert meta["author"] == "Author Name"
        assert meta["page_title"] == "Page Title"

    def test_empty_html(self):
        meta = extract_og_metadata("")
        assert meta == {}


class TestTruncateText:
    def test_no_truncation(self):
        text, truncated = truncate_text("hello world", 100)
        assert text == "hello world"
        assert not truncated

    def test_truncation(self):
        text, truncated = truncate_text("hello world foo bar", 12)
        assert truncated
        assert len(text) <= 12

    def test_zero_max_chars(self):
        text, truncated = truncate_text("hello", 0)
        assert text == "hello"
        assert not truncated
