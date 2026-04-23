from __future__ import annotations

import re


_THEME_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "dsa",
        (
            "dsa",
            "algorithm",
            "algorithms",
            "data structure",
            "data structures",
            "leetcode",
        ),
    ),
    (
        "career",
        (
            "career",
            "job search",
            "resume",
            "interview prep",
            "interview",
            "hiring",
        ),
    ),
    (
        "self-hosted",
        (
            "self-hosted",
            "self hosted",
            "homelab",
            "docker compose",
            "docker-compose",
            "kubernetes",
            "k8s",
            "vps",
        ),
    ),
    (
        "agentic-ai",
        (
            "agentic ai",
            "agentic-ai",
            "ai agent",
            "ai agents",
            "llm agent",
            "llm agents",
            "agent workflow",
            "agent workflows",
            "agents",
        ),
    ),
    (
        "ml-systems",
        (
            "ml systems",
            "machine learning systems",
            "model serving",
            "serving infrastructure",
            "training infrastructure",
            "inference stack",
            "rag",
        ),
    ),
)


def assign_theme_tags(*signals: str, source_tags: list[str] | None = None) -> list[str]:
    """Map source signals into a small stable set of theme tags."""
    parts = [signal for signal in signals if signal]
    if source_tags:
        parts.extend(source_tags)
    haystack = _normalize_text(" ".join(parts))

    tags: list[str] = []
    for assigned, patterns in _THEME_RULES:
        if any(_matches_pattern(haystack, pattern) for pattern in patterns):
            tags.append(assigned)
    return tags


def _normalize_text(text: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    return f" {normalized} "


def _matches_pattern(haystack: str, pattern: str) -> bool:
    normalized_pattern = _normalize_text(pattern)
    return normalized_pattern in haystack
