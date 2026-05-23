"""Markdown vault sink implementation."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from app.artifacts.models import (
    ArtifactBundle,
    ConceptArtifact,
    EntityArtifact,
    SynthesisArtifact,
    TopicArtifact,
)
from app.artifacts.vault_payloads import source_note_payload
from app.events import EventType, publish
from app.models.knowledge import Concept, Entity, SynthesisNote, Topic
from app.models.results import VaultUpdate
from app.models.source import SourceContent
from app.read_model.store import ReadModelStore
from app.storage.evidence import (
    EvidenceStoragePolicy,
    merge_existing_storage_metadata,
    prepare_evidence_storage,
)
from app.utils.markdown import parse_frontmatter, wikilink
from app.vault import paths, templates
from app.vault.index_updater import rebuild_indexes

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RawCaptureWriteResult:
    content: SourceContent
    raw_update: VaultUpdate
    auxiliary_updates: list[VaultUpdate]


class MarkdownVaultSink:
    """Default sink that renders canonical artifacts into the markdown vault."""

    sink_id = "markdown_vault"

    def __init__(
        self,
        vault_path: Path,
        *,
        storage_policy: EvidenceStoragePolicy | None = None,
    ):
        self.vault_path = vault_path
        self.storage_policy = storage_policy or EvidenceStoragePolicy()

    def ensure_structure(self) -> None:
        paths.ensure_vault_dirs(self.vault_path)

    def publish(
        self,
        *,
        content: SourceContent,
        bundle: ArtifactBundle,
    ) -> list[VaultUpdate]:
        """Publish canonical artifacts into the current markdown vault layout."""
        self.ensure_structure()
        updates = self.write_artifact_bundle(content=content, bundle=bundle)
        index_paths = rebuild_indexes(self.vault_path)
        self._refresh_read_model([update.path for update in updates] + index_paths)
        return updates

    def write_raw_capture(self, content: SourceContent, slug: str) -> VaultUpdate:
        return self._write_raw_capture_with_storage(content, slug).raw_update

    def write_artifact_bundle(
        self,
        *,
        content: SourceContent,
        bundle: ArtifactBundle,
    ) -> list[VaultUpdate]:
        source = bundle.source
        raw_result = self._write_raw_capture_with_storage(content, source.slug)
        raw_update = raw_result.raw_update
        source_payload = source_note_payload(bundle)

        updates = [
            *raw_result.auxiliary_updates,
            raw_update,
            self.write_source_note(
                content=raw_result.content,
                slug=source.slug,
                raw_capture_path=raw_update.path,
                quick_brief=source_payload["quick_brief"],
                summary=source_payload["summary"],
                five_minute_read=source_payload["five_minute_read"],
                detailed_reading_note=source_payload["detailed_reading_note"],
                best_next_action=source_payload["best_next_action"],
                theme_tags=source_payload["theme_tags"],
                brief_status=source_payload["brief_status"],
                watch_verdict=source_payload["watch_verdict"],
                watch_verdict_reasoning=source_payload["watch_verdict_reasoning"],
                quick_section_guide=source_payload["quick_section_guide"],
                detailed_sections=source_payload["detailed_sections"],
                signal_vs_filler=source_payload["signal_vs_filler"],
                important_terms=source_payload["important_terms"],
                key_ideas=source_payload["key_ideas"],
                detailed_outline=source_payload["detailed_outline"],
                important_examples=source_payload["important_examples"],
                actionable_takeaways=source_payload["takeaways"],
                notable_quotes=source_payload["notable_quotes"],
                best_for=source_payload["best_for"],
                consume_recommendation=source_payload["consume_recommendation"],
                why_it_matters=source_payload["why_it_matters"],
                open_questions=source_payload["open_questions"],
                topics=source_payload["topics"],
                entities=source_payload["entities"],
                concepts=source_payload["concepts"],
            ),
        ]

        for topic in bundle.topics:
            updates.append(self.write_topic_artifact(topic, bundle=bundle))

        for entity in bundle.entities:
            updates.append(self.write_entity_artifact(entity, bundle=bundle))

        for concept in bundle.concepts:
            updates.append(self.write_concept_artifact(concept, bundle=bundle))

        for synthesis in bundle.synthesis:
            updates.append(self.write_synthesis_artifact(synthesis))

        return updates

    def _write_raw_capture_with_storage(
        self,
        content: SourceContent,
        slug: str,
    ) -> RawCaptureWriteResult:
        raw_path = paths.raw_capture_path(self.vault_path, content.source.source_type, slug)
        if raw_path.exists():
            existing_meta, _ = parse_frontmatter(raw_path.read_text(encoding="utf-8"))
            stored_content = merge_existing_storage_metadata(content, existing_meta)
            rel = str(raw_path.relative_to(self.vault_path))
            return RawCaptureWriteResult(
                content=stored_content,
                raw_update=VaultUpdate(path=rel, action="unchanged", note_type="raw_capture"),
                auxiliary_updates=[],
            )

        prepared = prepare_evidence_storage(
            vault_path=self.vault_path,
            content=content,
            slug=slug,
            policy=self.storage_policy,
        )
        auxiliary_updates: list[VaultUpdate] = []
        if prepared.blob is not None:
            auxiliary_updates.append(
                self._write(
                    prepared.blob.absolute_path,
                    prepared.blob.payload,
                    "evidence_blob",
                )
            )
        raw_md = templates.raw_capture_md(prepared.content)
        raw_update = self._write(raw_path, raw_md, "raw_capture")
        return RawCaptureWriteResult(
            content=prepared.content,
            raw_update=raw_update,
            auxiliary_updates=auxiliary_updates,
        )

    def write_source_note(
        self,
        content: SourceContent,
        slug: str,
        raw_capture_path: str,
        *,
        quick_brief: str = "",
        summary: str,
        five_minute_read: str,
        detailed_reading_note: str,
        best_next_action: str = "",
        theme_tags: list[str] | None = None,
        brief_status: str = "partial",
        watch_verdict: str = "",
        watch_verdict_reasoning: str = "",
        quick_section_guide: str = "",
        detailed_sections: str = "",
        signal_vs_filler: str = "",
        important_terms: str = "",
        key_ideas: str,
        detailed_outline: str,
        important_examples: str,
        actionable_takeaways: str,
        notable_quotes: str,
        best_for: str,
        consume_recommendation: str,
        why_it_matters: str,
        open_questions: str,
        topics: list[str],
        entities: list[str],
        concepts: list[str],
    ) -> VaultUpdate:
        p = paths.source_note_path(self.vault_path, content.source.source_type, slug)
        existing_user_state = self._source_note_user_state(p)
        md = templates.source_note_md(
            content,
            raw_capture_path,
            quick_brief,
            summary,
            five_minute_read,
            detailed_reading_note,
            best_next_action,
            theme_tags or [],
            brief_status,
            watch_verdict,
            watch_verdict_reasoning,
            quick_section_guide,
            detailed_sections,
            signal_vs_filler,
            important_terms,
            key_ideas,
            detailed_outline,
            important_examples,
            actionable_takeaways,
            notable_quotes,
            best_for,
            consume_recommendation,
            why_it_matters,
            open_questions,
            topics,
            entities,
            concepts,
            user_state=existing_user_state,
        )
        return self._write(p, md, "source")

    def _source_note_user_state(self, path: Path) -> dict[str, object]:
        if not path.exists():
            return {}
        meta, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        user_state = meta.get("user_state")
        if isinstance(user_state, dict):
            return dict(user_state)
        return {}

    def write_topic(self, topic: Topic, source_titles: list[str]) -> VaultUpdate:
        p = paths.topic_note_path(self.vault_path, topic.slug)
        if p.exists():
            return self._update_topic(p, topic, source_titles)
        md = templates.topic_note_md(topic, source_titles)
        return self._write(p, md, "topic")

    def write_topic_artifact(
        self,
        topic: TopicArtifact,
        *,
        bundle: ArtifactBundle,
    ) -> VaultUpdate:
        p = paths.topic_note_path(self.vault_path, topic.slug)
        if p.exists():
            return self._update_topic_artifact(p, topic, bundle=bundle)
        md = templates.topic_artifact_note_md(
            topic,
            self._artifact_titles(topic.source_artifact_ids, bundle=bundle),
            related_concepts=self._artifact_titles(topic.related_concept_ids, bundle=bundle),
            related_entities=self._artifact_titles(topic.related_entity_ids, bundle=bundle),
        )
        return self._write(p, md, "topic")

    def write_entity(self, entity: Entity, source_titles: list[str]) -> VaultUpdate:
        p = paths.entity_note_path_for_type(self.vault_path, entity.slug, entity.entity_type)
        if p.exists():
            return self._update_entity(p, entity, source_titles)
        md = templates.entity_note_md(entity, source_titles)
        return self._write(p, md, "entity")

    def write_entity_artifact(
        self,
        entity: EntityArtifact,
        *,
        bundle: ArtifactBundle,
    ) -> VaultUpdate:
        p = paths.entity_note_path_for_type(self.vault_path, entity.slug, entity.entity_type)
        if p.exists():
            return self._update_entity_artifact(p, entity, bundle=bundle)
        md = templates.entity_artifact_note_md(
            entity,
            self._artifact_titles(entity.source_artifact_ids, bundle=bundle),
            related_concepts=self._artifact_titles(entity.related_concept_ids, bundle=bundle),
        )
        return self._write(p, md, "entity")

    def write_concept(self, concept: Concept, source_titles: list[str]) -> VaultUpdate:
        p = paths.concept_note_path(self.vault_path, concept.slug)
        if p.exists():
            return self._update_concept(p, concept, source_titles)
        md = templates.concept_note_md(concept, source_titles)
        return self._write(p, md, "concept")

    def write_concept_artifact(
        self,
        concept: ConceptArtifact,
        *,
        bundle: ArtifactBundle,
    ) -> VaultUpdate:
        p = paths.concept_note_path(self.vault_path, concept.slug)
        if p.exists():
            return self._update_concept_artifact(p, concept, bundle=bundle)
        md = templates.concept_artifact_note_md(
            concept,
            self._artifact_titles(concept.source_artifact_ids, bundle=bundle),
            related_concepts=self._artifact_titles(concept.related_concept_ids, bundle=bundle),
        )
        return self._write(p, md, "concept")

    def write_synthesis(self, note: SynthesisNote) -> VaultUpdate:
        p = paths.synthesis_note_path(self.vault_path, note.slug)
        md = templates.synthesis_note_md(note)
        return self._write(p, md, "synthesis")

    def write_synthesis_artifact(self, note: SynthesisArtifact) -> VaultUpdate:
        p = paths.synthesis_note_path(self.vault_path, note.slug)
        md = templates.synthesis_artifact_note_md(note)
        return self._write(p, md, "synthesis")

    def _write(self, path: Path, content: str, note_type: str) -> VaultUpdate:
        action = "updated" if path.exists() else "created"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        rel = str(path.relative_to(self.vault_path))
        update = VaultUpdate(path=rel, action=action, note_type=note_type)
        publish(
            EventType.ARTIFACT_WRITTEN,
            path=rel,
            note_type=note_type,
            action=action,
            sink_id=self.sink_id,
        )
        return update

    def _update_topic(self, path: Path, topic: Topic, source_titles: list[str]) -> VaultUpdate:
        _, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        sections = self._extract_sections(body)
        existing_sources = self._extract_section_list(body, "What I Have Saved")
        all_sources = list(dict.fromkeys(existing_sources + source_titles))
        existing_concepts = self._extract_section_list(body, "Related Concepts")
        existing_entities = self._extract_section_list(body, "Important Entities")
        merged_topic = topic.model_copy(
            update={
                "summary": self._clean_section_text(sections.get("Topic Summary", ""))
                or topic.summary,
                "related_concepts": list(dict.fromkeys(existing_concepts + topic.related_concepts)),
                "related_entities": list(dict.fromkeys(existing_entities + topic.related_entities)),
            }
        )
        if merged_topic.summary:
            sections["Topic Summary"] = merged_topic.summary
        sections["Related Concepts"] = self._render_wikilink_list(merged_topic.related_concepts)
        sections["Important Entities"] = self._render_wikilink_list(merged_topic.related_entities)
        md = templates.topic_note_md(merged_topic, all_sources, sections=sections)
        return self._write(path, md, "topic")

    def _update_topic_artifact(
        self,
        path: Path,
        topic: TopicArtifact,
        *,
        bundle: ArtifactBundle,
    ) -> VaultUpdate:
        _, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        sections = self._extract_sections(body)
        existing_sources = self._extract_section_list(body, "What I Have Saved")
        source_titles = self._artifact_titles(topic.source_artifact_ids, bundle=bundle)
        all_sources = list(dict.fromkeys(existing_sources + source_titles))
        existing_concepts = self._extract_section_list(body, "Related Concepts")
        existing_entities = self._extract_section_list(body, "Important Entities")
        related_concepts = list(
            dict.fromkeys(
                existing_concepts
                + self._artifact_titles(topic.related_concept_ids, bundle=bundle)
            )
        )
        related_entities = list(
            dict.fromkeys(
                existing_entities
                + self._artifact_titles(topic.related_entity_ids, bundle=bundle)
            )
        )
        if topic.summary and not self._clean_section_text(sections.get("Topic Summary", "")):
            sections["Topic Summary"] = topic.summary
        sections["Related Concepts"] = self._render_wikilink_list(related_concepts)
        sections["Important Entities"] = self._render_wikilink_list(related_entities)
        md = templates.topic_artifact_note_md(
            topic,
            all_sources,
            related_concepts=related_concepts,
            related_entities=related_entities,
            sections=sections,
        )
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
        if merged_entity.description:
            sections["What It Is"] = merged_entity.description
        sections["Related Concepts"] = self._render_wikilink_list(merged_entity.related_concepts)
        md = templates.entity_note_md(merged_entity, all_sources, sections=sections)
        return self._write(path, md, "entity")

    def _update_entity_artifact(
        self,
        path: Path,
        entity: EntityArtifact,
        *,
        bundle: ArtifactBundle,
    ) -> VaultUpdate:
        _, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        sections = self._extract_sections(body)
        existing_sources = self._extract_section_list(body, "Mentioned In")
        source_titles = self._artifact_titles(entity.source_artifact_ids, bundle=bundle)
        all_sources = list(dict.fromkeys(existing_sources + source_titles))
        existing_concepts = self._extract_section_list(body, "Related Concepts")
        related_concepts = list(
            dict.fromkeys(
                existing_concepts
                + self._artifact_titles(entity.related_concept_ids, bundle=bundle)
            )
        )
        if entity.summary and not self._clean_section_text(sections.get("What It Is", "")):
            sections["What It Is"] = entity.summary
        sections["Related Concepts"] = self._render_wikilink_list(related_concepts)
        md = templates.entity_artifact_note_md(
            entity,
            all_sources,
            related_concepts=related_concepts,
            sections=sections,
        )
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
        if merged_concept.definition:
            sections["Definition"] = merged_concept.definition
        sections["Related Concepts"] = self._render_wikilink_list(merged_concept.related_concepts)
        md = templates.concept_note_md(merged_concept, all_sources, sections=sections)
        return self._write(path, md, "concept")

    def _update_concept_artifact(
        self,
        path: Path,
        concept: ConceptArtifact,
        *,
        bundle: ArtifactBundle,
    ) -> VaultUpdate:
        _, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        sections = self._extract_sections(body)
        existing_sources = self._extract_section_list(body, "Where It Appears")
        source_titles = self._artifact_titles(concept.source_artifact_ids, bundle=bundle)
        all_sources = list(dict.fromkeys(existing_sources + source_titles))
        existing_related = self._extract_section_list(body, "Related Concepts")
        related_concepts = list(
            dict.fromkeys(
                existing_related
                + self._artifact_titles(concept.related_concept_ids, bundle=bundle)
            )
        )
        if concept.definition and not self._clean_section_text(sections.get("Definition", "")):
            sections["Definition"] = concept.definition
        sections["Related Concepts"] = self._render_wikilink_list(related_concepts)
        md = templates.concept_artifact_note_md(
            concept,
            all_sources,
            related_concepts=related_concepts,
            sections=sections,
        )
        return self._write(path, md, "concept")

    @staticmethod
    def _artifact_titles(artifact_ids: list[str], *, bundle: ArtifactBundle) -> list[str]:
        artifacts = bundle.artifact_index()
        return [
            artifacts[artifact_id].title
            for artifact_id in artifact_ids
            if artifact_id in artifacts
        ]

    @staticmethod
    def _extract_section_list(body: str, section_heading: str) -> list[str]:
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
                matches = re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", line)
                if matches:
                    items.extend(matches)
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

    @staticmethod
    def _render_wikilink_list(items: list[str]) -> str:
        return ", ".join(wikilink(item) for item in items) if items else "_None yet_"

    def _refresh_read_model(self, rel_paths: list[str]) -> None:
        try:
            ReadModelStore(self.vault_path).refresh_paths(rel_paths)
        except Exception:
            logger.warning("Read model refresh failed after markdown sink publish", exc_info=True)
