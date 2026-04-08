"""Tests for URL classification."""

from app.connectors.classifier import classify_url
from app.models.source import SourceType


class TestClassifyUrl:
    def test_youtube_watch(self):
        assert classify_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == SourceType.YOUTUBE

    def test_youtube_short_url(self):
        assert classify_url("https://youtu.be/dQw4w9WgXcQ") == SourceType.YOUTUBE

    def test_youtube_embed(self):
        assert classify_url("https://youtube.com/embed/dQw4w9WgXcQ") == SourceType.YOUTUBE

    def test_youtube_shorts(self):
        assert classify_url("https://youtube.com/shorts/dQw4w9WgXcQ") == SourceType.YOUTUBE

    def test_twitter_status(self):
        assert classify_url("https://twitter.com/user/status/123456") == SourceType.X_THREAD

    def test_x_status(self):
        assert classify_url("https://x.com/user/status/123456") == SourceType.X_THREAD

    def test_x_profile(self):
        assert classify_url("https://x.com/someuser") == SourceType.X_THREAD

    def test_pdf_url(self):
        assert classify_url("https://example.com/paper.pdf") == SourceType.PDF

    def test_pdf_url_case_insensitive(self):
        assert classify_url("https://example.com/Paper.PDF") == SourceType.PDF

    def test_article_url(self):
        assert classify_url("https://blog.example.com/great-article") == SourceType.ARTICLE

    def test_generic_article_fallback(self):
        assert classify_url("https://example.com/some-page") == SourceType.GENERIC

    def test_generic_root_url(self):
        assert classify_url("https://example.com/") == SourceType.GENERIC

    def test_article_slug_on_main_domain(self):
        assert (
            classify_url("https://example.com/notes/why-retrieval-augmented-generation-matters")
            == SourceType.ARTICLE
        )

    def test_url_with_query_params(self):
        url = "https://youtube.com/watch?v=abc123&t=100"
        assert classify_url(url) == SourceType.YOUTUBE
