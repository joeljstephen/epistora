"""Load editable markdown prompt templates for compiler workflows."""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.config import project_root

PROMPTS_ENV_VAR = "EPISTORA_PROMPTS_DIR"


def _prompt_roots() -> tuple[Path, ...]:
    roots: list[Path] = []

    override = os.environ.get(PROMPTS_ENV_VAR, "").strip()
    if override:
        roots.append(Path(override).expanduser())

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


def get_system_role() -> str:
    return _load_prompt("system_role.md")


def get_youtube_analysis_rules() -> str:
    return _load_prompt("ingest/youtube_rules.md")


def get_youtube_chunk_digest_system() -> str:
    return _load_prompt("ingest/youtube_chunk_digest_system.md")


def get_youtube_chunk_digest_user() -> str:
    return _load_prompt("ingest/youtube_chunk_digest_user.md")


def get_source_analysis_prompt(source_type: str | None = None) -> str:
    candidates: list[str] = []
    if source_type:
        candidates.append(f"ingest/source_analysis.{source_type}.md")
    candidates.append("ingest/source_analysis.md")
    return _load_prompt(*candidates)


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


SOURCE_ANALYSIS_JSON_SCHEMA = json.dumps(
    {
        "type": "object",
        "required": [
            "summary",
            "five_minute_read",
            "detailed_reading_note",
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
            "summary": {"type": "string"},
            "five_minute_read": {"type": "string"},
            "detailed_reading_note": {"type": "string"},
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
