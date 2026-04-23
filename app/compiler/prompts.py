"""Prompt loading and layered composition for compiler workflows."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.backends.models import TaskName
from app.config import Settings, get_settings, project_root
from app.plugins.loader import active_prompt_pack_root

PROMPTS_ENV_VAR = "EPISTORA_PROMPTS_DIR"
PROMPT_PACK_ENV_VAR = "EPISTORA_PROMPT_PACK"
PROMPT_PROFILE_ENV_VAR = "EPISTORA_PROMPT_PROFILE"
PROMPT_USER_OVERRIDE_ENV_VAR = "EPISTORA_PROMPT_USER_OVERRIDE"


@dataclass(frozen=True)
class PromptLayer:
    """A resolved prompt layer."""

    name: str
    precedence: int
    source: str
    content: str


@dataclass(frozen=True)
class ComposedPrompt:
    """Inspectable composed prompts passed to compiler backends."""

    task_name: str
    system_prompt: str
    user_prompt: str
    layers: tuple[PromptLayer, ...]

    def inspect(self) -> str:
        """Return a readable debug view of the composed prompt."""
        sections = [f"# Prompt Composition: {self.task_name}"]
        for layer in self.layers:
            sections.append(
                "\n".join(
                    [
                        f"## {layer.precedence}. {layer.name}",
                        f"Source: {layer.source}",
                        layer.content,
                    ]
                )
            )
        sections.append("## Final System Prompt")
        sections.append(self.system_prompt)
        sections.append("## Final User Prompt")
        sections.append(self.user_prompt)
        return "\n\n".join(section for section in sections if section)


def _prompt_roots() -> tuple[Path, ...]:
    roots: list[Path] = []

    override = os.environ.get(PROMPTS_ENV_VAR, "").strip()
    if override:
        roots.append(Path(override).expanduser())

    prompt_pack_root = active_prompt_pack_root()
    if prompt_pack_root is not None:
        roots.append(prompt_pack_root)

    roots.append(project_root() / "prompts")

    unique: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        resolved = root.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)

    return tuple(unique)


def _load_prompt(*relative_paths: str, required: bool = True) -> str:
    searched: list[Path] = []

    for root in _prompt_roots():
        for relative_path in relative_paths:
            candidate = root / relative_path
            searched.append(candidate)
            if candidate.exists():
                return candidate.read_text(encoding="utf-8").strip()

    if not required:
        return ""

    searched_str = "\n".join(f"- {path}" for path in searched)
    raise FileNotFoundError(
        "Prompt template not found. Checked:\n"
        f"{searched_str}\n"
        f"Set {PROMPTS_ENV_VAR} to point at a custom prompt directory if needed."
    )


def _load_all_prompts(*relative_paths: str) -> list[tuple[str, str]]:
    matches: list[tuple[str, str]] = []
    seen_paths: set[Path] = set()

    for root in _prompt_roots():
        for relative_path in relative_paths:
            candidate = (root / relative_path).resolve()
            if not candidate.exists() or candidate in seen_paths:
                continue
            seen_paths.add(candidate)
            matches.append((str(candidate), candidate.read_text(encoding="utf-8").strip()))

    return matches


def _task_template_paths(task_name: str, source_type: str | None = None) -> tuple[str, ...]:
    if task_name == "ingest_analysis":
        paths: list[str] = []
        if source_type:
            paths.append(f"ingest/source_analysis.{source_type}.md")
        paths.append("ingest/source_analysis.md")
        return tuple(paths)
    if task_name == "query_answer":
        return ("query/query.md",)
    if task_name == "topic_bundle":
        return ("topic/topic_bundle.md",)
    if task_name == "lint_analysis":
        return ("lint/lint_analysis.md",)
    raise ValueError(f"Unsupported prompt task '{task_name}'")


def get_system_role() -> str:
    return _load_prompt("system_role.md")


def get_youtube_analysis_rules() -> str:
    return _load_prompt("ingest/youtube_rules.md")


def get_youtube_chunk_digest_system() -> str:
    return _load_prompt("ingest/youtube_chunk_digest_system.md")


def get_youtube_chunk_digest_user() -> str:
    return _load_prompt("ingest/youtube_chunk_digest_user.md")


def get_source_analysis_prompt(source_type: str | None = None) -> str:
    return _load_prompt(*_task_template_paths("ingest_analysis", source_type))


def get_source_guidance_markdown(source_type: str | None = None) -> str:
    parts = [_load_prompt("ingest/source_guidance/common.md", required=False)]
    if source_type:
        parts.append(
            _load_prompt(f"ingest/source_guidance/{source_type}.md", required=False)
        )
    return "\n\n".join(part for part in parts if part)


def get_query_prompt() -> str:
    return _load_prompt("query/query.md")


def get_lint_analysis_prompt() -> str:
    return _load_prompt("lint/lint_analysis.md")


def compose_ingest_analysis_prompt(
    *,
    source_type: str,
    workspace_path: Path | None,
    format_kwargs: dict[str, Any],
    source_type_instructions: str,
    settings: Settings | None = None,
    user_override: str = "",
) -> ComposedPrompt:
    return compose_prompt(
        task_name="ingest_analysis",
        artifact_type="source",
        source_type=source_type,
        workspace_path=workspace_path,
        format_kwargs=format_kwargs,
        source_type_instructions=source_type_instructions,
        settings=settings,
        user_override=user_override,
    )


def compose_query_prompt(
    *,
    workspace_path: Path | None,
    format_kwargs: dict[str, Any],
    settings: Settings | None = None,
    user_override: str = "",
) -> ComposedPrompt:
    return compose_prompt(
        task_name="query_answer",
        artifact_type="query",
        workspace_path=workspace_path,
        format_kwargs=format_kwargs,
        settings=settings,
        user_override=user_override,
    )


def compose_topic_bundle_prompt(
    *,
    workspace_path: Path | None,
    format_kwargs: dict[str, Any],
    settings: Settings | None = None,
    user_override: str = "",
) -> ComposedPrompt:
    return compose_prompt(
        task_name="topic_bundle",
        artifact_type="topic_bundle",
        workspace_path=workspace_path,
        format_kwargs=format_kwargs,
        settings=settings,
        user_override=user_override,
    )


def compose_lint_prompt(
    *,
    workspace_path: Path | None,
    format_kwargs: dict[str, Any],
    settings: Settings | None = None,
    user_override: str = "",
) -> ComposedPrompt:
    return compose_prompt(
        task_name="lint_analysis",
        artifact_type="lint",
        workspace_path=workspace_path,
        format_kwargs=format_kwargs,
        settings=settings,
        user_override=user_override,
    )


def compose_prompt(
    *,
    task_name: str,
    artifact_type: str = "",
    source_type: str = "",
    workspace_path: Path | None = None,
    format_kwargs: dict[str, Any] | None = None,
    source_type_instructions: str = "",
    settings: Settings | None = None,
    user_override: str = "",
) -> ComposedPrompt:
    resolved_settings = settings or get_settings()
    base_template = _load_prompt(
        *_task_template_paths(
            task_name,
            source_type if task_name == "ingest_analysis" else None,
        )
    )
    base_system = get_system_role()
    profile = os.environ.get(PROMPT_PROFILE_ENV_VAR, "").strip()
    backend_id, model_id = _task_backend_hint(task_name, resolved_settings)

    layers: list[PromptLayer] = [
        PromptLayer(
            name="base compiler instructions",
            precedence=1,
            source="system_role.md",
            content=base_system,
        )
    ]

    artifact_text, artifact_sources = _artifact_instructions(artifact_type)
    if artifact_text:
        layers.append(
            PromptLayer(
                name="artifact-type instructions",
                precedence=2,
                source=artifact_sources,
                content=artifact_text,
            )
        )

    if source_type_instructions:
        layers.append(
            PromptLayer(
                name="source-type instructions",
                precedence=3,
                source=f"source guidance ({source_type or 'none'})",
                content=source_type_instructions,
            )
        )

    workspace_profile_text, workspace_profile_sources = _workspace_profile_instructions(
        task_name=task_name,
        workspace_path=workspace_path,
        profile=profile,
    )
    if workspace_profile_text:
        layers.append(
            PromptLayer(
                name="workspace/profile instructions",
                precedence=4,
                source=workspace_profile_sources,
                content=workspace_profile_text,
            )
        )

    override_text = user_override.strip() or os.environ.get(
        PROMPT_USER_OVERRIDE_ENV_VAR,
        "",
    ).strip()
    if override_text:
        layers.append(
            PromptLayer(
                name="user overrides",
                precedence=5,
                source="explicit override",
                content=override_text,
            )
        )

    backend_hint_text, backend_hint_sources = _backend_model_hints(
        task_name=task_name,
        backend_id=backend_id,
        model_id=model_id,
    )
    if backend_hint_text:
        layers.append(
            PromptLayer(
                name="backend/model-specific hints",
                precedence=6,
                source=backend_hint_sources,
                content=backend_hint_text,
            )
        )

    layer_text_by_name = {layer.name: layer.content for layer in layers}
    format_context = dict(format_kwargs or {})
    format_context.setdefault(
        "artifact_type_instructions",
        layer_text_by_name.get("artifact-type instructions", ""),
    )
    format_context.setdefault(
        "source_type_instructions",
        layer_text_by_name.get("source-type instructions", ""),
    )
    format_context.setdefault(
        "source_specific_guidance",
        layer_text_by_name.get("source-type instructions", ""),
    )
    format_context.setdefault(
        "workspace_profile_instructions",
        layer_text_by_name.get("workspace/profile instructions", ""),
    )
    format_context.setdefault(
        "user_override_instructions",
        layer_text_by_name.get("user overrides", ""),
    )
    format_context.setdefault(
        "backend_model_hints",
        layer_text_by_name.get("backend/model-specific hints", ""),
    )

    user_prompt = base_template.format(**format_context)
    appended_layers = _appended_layer_sections(base_template=base_template, layers=layers[1:])
    if appended_layers:
        user_prompt = f"{user_prompt}\n\nAdditional layered instructions:\n\n{appended_layers}"

    return ComposedPrompt(
        task_name=task_name,
        system_prompt=base_system,
        user_prompt=user_prompt,
        layers=tuple(layers),
    )


def _artifact_instructions(artifact_type: str) -> tuple[str, str]:
    if not artifact_type:
        return "", ""
    return _join_matches(_load_all_prompts(f"layers/artifact/{artifact_type}.md"))


def _workspace_prompt_root(workspace_path: Path | None) -> Path | None:
    if workspace_path is None:
        return None
    return workspace_path / ".system" / "prompts"


def _workspace_profile_instructions(
    *,
    task_name: str,
    workspace_path: Path | None,
    profile: str,
) -> tuple[str, str]:
    matches: list[tuple[str, str]] = []

    if profile:
        matches.extend(
            _load_all_prompts(
                f"profiles/{profile}/common.md",
                f"profiles/{profile}/tasks/{task_name}.md",
            )
        )

    workspace_root = _workspace_prompt_root(workspace_path)
    if workspace_root and workspace_root.exists():
        relative_paths = ["common.md", f"tasks/{task_name}.md"]
        if profile:
            relative_paths.extend(
                [
                    f"profiles/{profile}/common.md",
                    f"profiles/{profile}/tasks/{task_name}.md",
                ]
            )
        for relative_path in relative_paths:
            candidate = workspace_root / relative_path
            if candidate.exists():
                matches.append(
                    (
                        str(candidate.resolve()),
                        candidate.read_text(encoding="utf-8").strip(),
                    )
                )

    return _join_matches(matches)


def _backend_model_hints(
    *,
    task_name: str,
    backend_id: str,
    model_id: str,
) -> tuple[str, str]:
    if not backend_id:
        return "", ""

    matches = _load_all_prompts(f"backend_hints/{task_name}/{backend_id}.md")
    model_token = _model_hint_token(model_id)
    if model_token:
        matches.extend(
            _load_all_prompts(
                f"backend_hints/{task_name}/{backend_id}.{model_token}.md"
            )
        )
    return _join_matches(matches)


def _task_backend_hint(task_name: str, settings: Settings) -> tuple[str, str]:
    task = _task_enum(task_name)
    raw_order = {
        TaskName.INGEST: settings.backend_order_ingest,
        TaskName.QUERY: settings.backend_order_query,
        TaskName.TOPIC_BUNDLE: settings.backend_order_query,
        TaskName.LINT: settings.backend_order_lint,
    }[task]
    token = raw_order.split(",", 1)[0] if raw_order else ""
    backend_id = _normalize_backend_token(token)
    if not backend_id:
        return "", ""
    return backend_id, _task_model_hint(task, backend_id, settings)


def _task_enum(task_name: str) -> TaskName:
    return {
        "ingest_analysis": TaskName.INGEST,
        "query_answer": TaskName.QUERY,
        "topic_bundle": TaskName.TOPIC_BUNDLE,
        "lint_analysis": TaskName.LINT,
    }[task_name]


def _normalize_backend_token(token: str) -> str:
    normalized = token.strip().lower()
    aliases = {
        "api": "api",
        "opencode": "opencode",
        "open_code": "opencode",
        "claude": "claude_code",
        "claude-code": "claude_code",
        "claude_code": "claude_code",
        "codex": "codex",
    }
    return aliases.get(normalized, normalized)


def _task_model_hint(task: TaskName, backend_id: str, settings: Settings) -> str:
    suffix = {
        TaskName.INGEST: "ingest",
        TaskName.QUERY: "query",
        TaskName.TOPIC_BUNDLE: "query",
        TaskName.LINT: "lint",
    }[task]
    if backend_id == "api":
        return getattr(settings, f"api_model_{suffix}", "") or settings.effective_api_model()
    if backend_id == "opencode":
        return getattr(settings, f"opencode_model_{suffix}", "") or settings.opencode_model
    if backend_id == "claude_code":
        return (
            getattr(settings, f"claude_code_model_{suffix}", "")
            or settings.claude_code_model
        )
    if backend_id == "codex":
        return getattr(settings, f"codex_model_{suffix}", "") or settings.codex_model
    return ""


def _model_hint_token(model_id: str) -> str:
    if not model_id:
        return ""
    normalized = "".join(char.lower() if char.isalnum() else "_" for char in model_id)
    return "_".join(part for part in normalized.split("_") if part)


def _appended_layer_sections(*, base_template: str, layers: list[PromptLayer]) -> str:
    placeholder_map = {
        "artifact-type instructions": ("artifact_type_instructions",),
        "source-type instructions": (
            "source_specific_guidance",
            "source_type_instructions",
        ),
        "workspace/profile instructions": ("workspace_profile_instructions",),
        "user overrides": ("user_override_instructions",),
        "backend/model-specific hints": ("backend_model_hints",),
    }
    sections: list[str] = []
    for layer in layers:
        placeholder_names = placeholder_map.get(layer.name, ())
        if not layer.content:
            continue
        has_inline_placeholder = any(
            f"{{{placeholder_name}}}" in base_template
            for placeholder_name in placeholder_names
        )
        if has_inline_placeholder:
            continue
        sections.append(f"### {layer.name.title()}\n{layer.content}")
    return "\n\n".join(sections)


def _join_matches(matches: list[tuple[str, str]]) -> tuple[str, str]:
    contents = [content for _, content in matches if content]
    sources = [source for source, content in matches if content]
    return "\n\n".join(contents), "\n".join(sources)


SOURCE_ANALYSIS_JSON_SCHEMA = json.dumps(
    {
        "type": "object",
        "required": [
            "quick_brief",
            "summary",
            "five_minute_read",
            "detailed_reading_note",
            "best_next_action",
            "watch_verdict",
            "watch_verdict_reasoning",
            "quick_section_guide",
            "detailed_sections",
            "signal_vs_filler",
            "important_terms",
            "key_ideas",
            "detailed_outline",
            "important_examples",
            "actionable_takeaways",
            "notable_quotes",
            "best_for",
            "consume_recommendation",
            "why_it_matters",
            "open_questions",
            "topics",
            "entities",
            "concepts",
        ],
        "properties": {
            "quick_brief": {"type": "string"},
            "summary": {"type": "string"},
            "five_minute_read": {"type": "string"},
            "detailed_reading_note": {"type": "string"},
            "best_next_action": {"type": "string"},
            "watch_verdict": {"type": "string"},
            "watch_verdict_reasoning": {"type": "string"},
            "quick_section_guide": {"type": "string"},
            "detailed_sections": {"type": "string"},
            "signal_vs_filler": {"type": "string"},
            "important_terms": {"type": "array", "items": {"type": "string"}},
            "key_ideas": {"type": "string"},
            "detailed_outline": {"type": "string"},
            "important_examples": {"type": "string"},
            "actionable_takeaways": {"type": "string"},
            "notable_quotes": {"type": "string"},
            "best_for": {"type": "string"},
            "consume_recommendation": {"type": "string"},
            "why_it_matters": {"type": "string"},
            "open_questions": {"type": "string"},
            "topics": {"type": "array", "items": {"type": "string"}},
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["name", "type", "description"],
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "additionalProperties": True,
                },
            },
            "concepts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["name", "definition"],
                    "properties": {
                        "name": {"type": "string"},
                        "definition": {"type": "string"},
                    },
                    "additionalProperties": True,
                },
            },
        },
        "additionalProperties": True,
    }
)

LINT_ANALYSIS_JSON_SCHEMA = json.dumps(
    {
        "type": "object",
        "required": [
            "duplicate_candidates",
            "potential_contradictions",
            "missing_pages",
            "merge_candidates",
            "navigation_gaps",
            "thin_pages",
        ],
        "properties": {
            "duplicate_candidates": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": True},
            },
            "potential_contradictions": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": True},
            },
            "missing_pages": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": True},
            },
            "merge_candidates": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": True},
            },
            "navigation_gaps": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": True},
            },
            "thin_pages": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": True},
            },
        },
        "additionalProperties": True,
    }
)
