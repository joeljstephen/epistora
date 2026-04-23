"""Tests for prompt loading and layered composition."""

from __future__ import annotations

from pathlib import Path

from app.compiler.prompts import (
    compose_prompt,
    get_source_analysis_prompt,
    get_source_guidance_markdown,
    get_system_role,
)
from app.config import Settings


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


def test_compose_prompt_layers_follow_precedence(monkeypatch, tmp_path: Path):
    prompts_dir = tmp_path / "custom-prompts"
    _write(prompts_dir / "system_role.md", "System role")
    _write(prompts_dir / "query" / "query.md", "Question: {question}\nContext: {context}")
    _write(prompts_dir / "layers" / "artifact" / "query.md", "Artifact layer")
    _write(prompts_dir / "profiles" / "research" / "common.md", "Profile common")
    _write(
        prompts_dir / "profiles" / "research" / "tasks" / "query_answer.md",
        "Profile task",
    )
    _write(prompts_dir / "backend_hints" / "query_answer" / "api.md", "Backend hint")
    _write(
        prompts_dir / "backend_hints" / "query_answer" / "api.gpt_4o_mini.md",
        "Model hint",
    )

    workspace = tmp_path / "vault"
    _write(workspace / ".system" / "prompts" / "common.md", "Workspace common")
    _write(
        workspace / ".system" / "prompts" / "tasks" / "query_answer.md",
        "Workspace task",
    )

    monkeypatch.setenv("EPISTORA_PROMPTS_DIR", str(prompts_dir))
    monkeypatch.setenv("EPISTORA_PROMPT_PROFILE", "research")

    composed = compose_prompt(
        task_name="query_answer",
        artifact_type="query",
        workspace_path=workspace,
        format_kwargs={"question": "Q", "context": "C"},
        settings=Settings(
            backend_order_query="api",
            api_model="gpt-4o-mini",
        ),
        user_override="User override",
    )

    assert [layer.name for layer in composed.layers] == [
        "base compiler instructions",
        "artifact-type instructions",
        "workspace/profile instructions",
        "user overrides",
        "backend/model-specific hints",
    ]
    assert "Artifact layer" in composed.user_prompt
    assert "Profile common" in composed.user_prompt
    assert "Workspace common" in composed.user_prompt
    assert "User override" in composed.user_prompt
    assert "Backend hint" in composed.user_prompt
    assert "Model hint" in composed.user_prompt


def test_compose_prompt_inspection_includes_final_prompts(monkeypatch, tmp_path: Path):
    prompts_dir = tmp_path / "custom-prompts"
    _write(prompts_dir / "system_role.md", "System role")
    _write(prompts_dir / "query" / "query.md", "Question: {question}\nContext: {context}")
    monkeypatch.setenv("EPISTORA_PROMPTS_DIR", str(prompts_dir))

    composed = compose_prompt(
        task_name="query_answer",
        artifact_type="query",
        workspace_path=None,
        format_kwargs={"question": "Q", "context": "C"},
    )

    debug_view = composed.inspect()
    assert "# Prompt Composition: query_answer" in debug_view
    assert "## Final System Prompt" in debug_view
    assert "## Final User Prompt" in debug_view
    assert "Question: Q" in debug_view


def test_compose_prompt_uses_placeholder_instead_of_duplicate_append(
    monkeypatch,
    tmp_path: Path,
):
    prompts_dir = tmp_path / "custom-prompts"
    _write(prompts_dir / "system_role.md", "System role")
    _write(
        prompts_dir / "ingest" / "source_analysis.md",
        "Guidance:\n{source_specific_guidance}\nBody:\n{content}",
    )
    monkeypatch.setenv("EPISTORA_PROMPTS_DIR", str(prompts_dir))

    composed = compose_prompt(
        task_name="ingest_analysis",
        artifact_type="source",
        source_type="article",
        workspace_path=None,
        format_kwargs={"content": "Evidence"},
        source_type_instructions="Layered source guidance",
    )

    assert composed.user_prompt.count("Layered source guidance") == 1


def test_prompt_override_directory_wins_over_plugin_pack(monkeypatch, tmp_path: Path):
    plugin_root = tmp_path / "plugins"
    plugin_dir = plugin_root / "research_pack"
    prompt_dir = plugin_dir / "prompts"
    override_dir = tmp_path / "override"

    _write(
        plugin_dir / "epistora-plugin.toml",
        """
[plugin]
id = "research_pack"
name = "Research Pack"
version = "0.1.0"
type = "prompt_pack"

[compatibility]
min_epistora_version = "0.1.0"

[entrypoints]
prompt_pack_dir = "prompts"
""".strip(),
    )
    _write(prompt_dir / "system_role.md", "Plugin role")
    _write(override_dir / "system_role.md", "Override role")

    monkeypatch.setenv("EPISTORA_PLUGIN_DIRS", str(plugin_root))
    monkeypatch.setenv("EPISTORA_PROMPT_PACK", "research_pack")
    monkeypatch.setenv("EPISTORA_PROMPTS_DIR", str(override_dir))

    assert get_system_role() == "Override role"


def test_personal_learning_profile_common_instructions_are_loaded(monkeypatch):
    monkeypatch.delenv("EPISTORA_PROMPTS_DIR", raising=False)
    monkeypatch.setenv("EPISTORA_PROMPT_PROFILE", "personal_learning")

    composed = compose_prompt(
        task_name="query_answer",
        artifact_type="query",
        workspace_path=None,
        format_kwargs={"question": "Q", "context": "C"},
    )

    assert "Favor personal-learning outcomes over exhaustive analysis." in composed.user_prompt
