"""Resolve topic/entity/concept names to existing vault pages."""

from __future__ import annotations

from pathlib import Path

from app.utils.slugify import slugify
from app.vault import paths


def resolve_topic(vault_path: Path, name: str) -> Path | None:
    p = paths.topic_note_path(vault_path, slugify(name))
    return p if p.exists() else None


def resolve_entity(vault_path: Path, name: str) -> Path | None:
    p = paths.entity_note_path(vault_path, slugify(name))
    return p if p.exists() else None


def resolve_concept(vault_path: Path, name: str) -> Path | None:
    p = paths.concept_note_path(vault_path, slugify(name))
    return p if p.exists() else None


def resolve_any(vault_path: Path, name: str) -> Path | None:
    """Try to resolve a name to any existing vault page."""
    for resolver in (resolve_topic, resolve_entity, resolve_concept):
        result = resolver(vault_path, name)
        if result:
            return result
    return None
