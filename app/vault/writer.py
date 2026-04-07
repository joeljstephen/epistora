"""Writes and updates markdown files in the vault."""

from __future__ import annotations

import re
from pathlib import Path

from app.models.knowledge import Concept, Entity, SynthesisNote, Topic
from app.models.results import VaultUpdate
from app.models.source import SourceContent
from app.utils.markdown import parse_frontmatter
from app.vault import paths, templates


class VaultWriter:
    def __init__(self, vault_path: Path):
        self.vault_path = vault_path

    def ensure_structure(self) -> None:
        paths.ensure_vault_dirs(self.vault_path)

    def write_raw_capture(self, content: SourceContent, slug: str) -> VaultUpdate:
        p = paths.raw_capture_path(self.vault_path, content.source.source_type, slug)
        md = templates.raw_capture_md(content)
        return self._write(p, md, "raw_capture")

    def write_source_note(
        self,
        content: SourceContent,
        slug: str,
        summary: str,
        key_takeaways: str,
        detailed_outline: str,
        important_claims: str,
        why_matters: str,
        open_questions: str,
        topics: list[str],
        entities: list[str],
        concepts: list[str],
    ) -> VaultUpdate:
        p = paths.source_note_path(self.vault_path, content.source.source_type, slug)
        md = templates.source_note_md(
            content,
            summary,
            key_takeaways,
            detailed_outline,
            important_claims,
            why_matters,
            open_questions,
            topics,
            entities,
            concepts,
        )
        return self._write(p, md, "source")

    def write_topic(self, topic: Topic, source_titles: list[str]) -> VaultUpdate:
        p = paths.topic_note_path(self.vault_path, topic.slug)
        if p.exists():
            return self._update_topic(p, topic, source_titles)
        md = templates.topic_note_md(topic, source_titles)
        return self._write(p, md, "topic")

    def write_entity(self, entity: Entity, source_titles: list[str]) -> VaultUpdate:
        p = paths.entity_note_path_for_type(self.vault_path, entity.slug, entity.entity_type)
        if p.exists():
            return self._update_entity(p, entity, source_titles)
        md = templates.entity_note_md(entity, source_titles)
        return self._write(p, md, "entity")

    def write_concept(self, concept: Concept, source_titles: list[str]) -> VaultUpdate:
        p = paths.concept_note_path(self.vault_path, concept.slug)
        if p.exists():
            return self._update_concept(p, concept, source_titles)
        md = templates.concept_note_md(concept, source_titles)
        return self._write(p, md, "concept")

    def write_synthesis(self, note: SynthesisNote) -> VaultUpdate:
        p = paths.synthesis_note_path(self.vault_path, note.slug)
        md = templates.synthesis_note_md(note)
        return self._write(p, md, "synthesis")

    def _write(self, path: Path, content: str, note_type: str) -> VaultUpdate:
        action = "updated" if path.exists() else "created"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        rel = str(path.relative_to(self.vault_path))
        return VaultUpdate(path=rel, action=action, note_type=note_type)

    def _update_topic(self, path: Path, topic: Topic, source_titles: list[str]) -> VaultUpdate:
        _, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        sections = self._extract_sections(body)
        existing_sources = self._extract_section_list(body, "What I Have Saved")
        all_sources = list(dict.fromkeys(existing_sources + source_titles))
        existing_concepts = self._extract_section_list(body, "Core Concepts")
        existing_entities = self._extract_section_list(body, "Important Entities")
        merged_topic = topic.model_copy(
            update={
                "summary": topic.summary
                or self._clean_section_text(sections.get("Topic Summary", "")),
                "related_concepts": list(dict.fromkeys(existing_concepts + topic.related_concepts)),
                "related_entities": list(dict.fromkeys(existing_entities + topic.related_entities)),
            }
        )
        md = templates.topic_note_md(merged_topic, all_sources, sections=sections)
        return self._write(path, md, "topic")

    def _update_entity(self, path: Path, entity: Entity, source_titles: list[str]) -> VaultUpdate:
        _, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        sections = self._extract_sections(body)
        existing_sources = self._extract_section_list(body, "Mentioned In")
        all_sources = list(dict.fromkeys(existing_sources + source_titles))
        existing_concepts = self._extract_section_list(body, "Related Concepts")
        merged_entity = entity.model_copy(
            update={
                "description": entity.description
                or self._clean_section_text(sections.get("What It Is", "")),
                "related_concepts": list(
                    dict.fromkeys(existing_concepts + entity.related_concepts)
                ),
            }
        )
        md = templates.entity_note_md(merged_entity, all_sources, sections=sections)
        return self._write(path, md, "entity")

    def _update_concept(
        self, path: Path, concept: Concept, source_titles: list[str]
    ) -> VaultUpdate:
        _, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        sections = self._extract_sections(body)
        existing_sources = self._extract_section_list(body, "Where It Appears")
        all_sources = list(dict.fromkeys(existing_sources + source_titles))
        existing_related = self._extract_section_list(body, "Related Concepts")
        merged_concept = concept.model_copy(
            update={
                "definition": concept.definition
                or self._clean_section_text(sections.get("Definition", "")),
                "related_concepts": list(
                    dict.fromkeys(existing_related + concept.related_concepts)
                ),
            }
        )
        md = templates.concept_note_md(merged_concept, all_sources, sections=sections)
        return self._write(path, md, "concept")

    @staticmethod
    def _extract_section_list(body: str, section_heading: str) -> list[str]:
        """Pull wikilink items from a bullet list under a given heading."""
        lines = body.split("\n")
        in_section = False
        items: list[str] = []
        for line in lines:
            if line.strip().startswith("## ") and section_heading in line:
                in_section = True
                continue
            if in_section:
                if line.strip().startswith("## "):
                    break
                match = re.search(r"\[\[([^\]]+)\]\]", line)
                if match:
                    items.append(match.group(1))
        return items

    @staticmethod
    def _extract_sections(body: str) -> dict[str, str]:
        sections: dict[str, list[str]] = {}
        current_heading: str | None = None

        for line in body.splitlines():
            if line.startswith("## "):
                current_heading = line[3:].strip()
                sections[current_heading] = []
                continue
            if current_heading is not None:
                sections[current_heading].append(line)

        return {heading: "\n".join(lines).strip() for heading, lines in sections.items()}

    @staticmethod
    def _clean_section_text(text: str) -> str:
        cleaned = text.strip()
        if not cleaned:
            return ""
        if re.fullmatch(r"_.*_", cleaned, flags=re.DOTALL):
            return ""
        return cleaned
