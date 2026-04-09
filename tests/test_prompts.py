"""Tests for file-based prompt template loading."""

from __future__ import annotations

from pathlib import Path

from app.compiler.prompts import (
    get_source_analysis_prompt,
    get_source_guidance_markdown,
    get_system_role,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_prompt_loader_uses_custom_prompt_directory(monkeypatch, tmp_path: Path):
    prompts_dir = tmp_path / "custom-prompts"
    _write(prompts_dir / "system_role.md", "Custom system role")

    monkeypatch.setenv("EPISTORA_PROMPTS_DIR", str(prompts_dir))

    assert get_system_role() == "Custom system role"


def test_source_analysis_prefers_source_specific_override(monkeypatch, tmp_path: Path):
    prompts_dir = tmp_path / "custom-prompts"
    _write(prompts_dir / "system_role.md", "System")
    _write(prompts_dir / "ingest" / "source_analysis.md", "default {title}")
    _write(prompts_dir / "ingest" / "source_analysis.youtube.md", "youtube {title}")

    monkeypatch.setenv("EPISTORA_PROMPTS_DIR", str(prompts_dir))

    assert get_source_analysis_prompt("youtube") == "youtube {title}"
    assert get_source_analysis_prompt("article") == "default {title}"


def test_source_guidance_combines_common_and_source_specific(monkeypatch, tmp_path: Path):
    prompts_dir = tmp_path / "custom-prompts"
    _write(prompts_dir / "system_role.md", "System")
    _write(prompts_dir / "ingest" / "source_guidance" / "common.md", "- shared")
    _write(prompts_dir / "ingest" / "source_guidance" / "pdf.md", "- pdf")

    monkeypatch.setenv("EPISTORA_PROMPTS_DIR", str(prompts_dir))

    assert get_source_guidance_markdown("pdf") == "- shared\n\n- pdf"
