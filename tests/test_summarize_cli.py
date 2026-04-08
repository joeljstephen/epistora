"""Tests for summarize.sh CLI wrapper behavior."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from app.config import Settings
from app.connectors.fetchers.summarize_cli import SummarizeResult, extract_url, is_available


def _settings(**overrides) -> Settings:
    values = {
        "summarize_enabled": True,
        "summarize_binary": "summarize",
        "summarize_timeout_seconds": 30,
    }
    values.update(overrides)
    return Settings(**values)


def _payload(content: str) -> str:
    return json.dumps(
        {
            "input": {"url": "https://example.com/article"},
            "extracted": {
                "url": "https://example.com/article",
                "title": "Example Title",
                "siteName": "Example",
                "content": content,
                "wordCount": 120,
                "transcriptSource": None,
                "diagnostics": {"strategy": "html"},
            },
        }
    )


def test_summarize_is_available_respects_setting_and_binary():
    with patch("app.connectors.fetchers.summarize_cli.shutil.which") as mock_which:
        mock_which.return_value = "/usr/bin/summarize"
        assert is_available(_settings()) is True
        assert is_available(_settings(summarize_enabled=False)) is False


@pytest.mark.asyncio
async def test_summarize_extract_url_successful_parse():
    completed = subprocess.CompletedProcess(
        args=["summarize"],
        returncode=0,
        stdout=_payload(
            "# Example Title\n\nThis is a long markdown extraction body.\n\nSecond paragraph here."
        ),
        stderr="",
    )

    with patch("app.connectors.fetchers.summarize_cli.shutil.which") as mock_which, patch(
        "app.connectors.fetchers.summarize_cli.subprocess.run"
    ) as mock_run:
        mock_which.return_value = "/usr/bin/summarize"
        mock_run.return_value = completed

        result = await extract_url(
            "https://example.com/article",
            source_kind="article",
            settings=_settings(),
        )

    assert isinstance(result, SummarizeResult)
    assert result.success is True
    assert result.title == "Example Title"
    assert "This is a long markdown extraction body." in result.cleaned_text
    assert result.archived_markdown.startswith("# Example Title")
    assert result.extraction_method == "summarize_cli"


@pytest.mark.asyncio
async def test_summarize_extract_url_timeout_handling():
    with patch("app.connectors.fetchers.summarize_cli.shutil.which") as mock_which, patch(
        "app.connectors.fetchers.summarize_cli.subprocess.run"
    ) as mock_run:
        mock_which.return_value = "/usr/bin/summarize"
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["summarize"], timeout=30)

        result = await extract_url(
            "https://example.com/article",
            source_kind="article",
            settings=_settings(),
        )

    assert result.success is False
    assert "timed out" in result.provider_notes


@pytest.mark.asyncio
async def test_summarize_extract_url_subprocess_error():
    with patch("app.connectors.fetchers.summarize_cli.shutil.which") as mock_which, patch(
        "app.connectors.fetchers.summarize_cli.subprocess.run"
    ) as mock_run:
        mock_which.return_value = "/usr/bin/summarize"
        mock_run.side_effect = OSError("spawn failed")

        result = await extract_url(
            "https://example.com/article",
            source_kind="article",
            settings=_settings(),
        )

    assert result.success is False
    assert "invocation failed" in result.provider_notes


@pytest.mark.asyncio
async def test_summarize_extract_url_invalid_output():
    completed = subprocess.CompletedProcess(
        args=["summarize"],
        returncode=0,
        stdout="not-json",
        stderr="",
    )

    with patch("app.connectors.fetchers.summarize_cli.shutil.which") as mock_which, patch(
        "app.connectors.fetchers.summarize_cli.subprocess.run"
    ) as mock_run:
        mock_which.return_value = "/usr/bin/summarize"
        mock_run.return_value = completed

        result = await extract_url(
            "https://example.com/article",
            source_kind="article",
            settings=_settings(),
        )

    assert result.success is False
    assert "invalid JSON" in result.provider_notes
