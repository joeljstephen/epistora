from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

from app.models.source import SourceContent, SourceType


class ReadVerdict(StrEnum):
    READ = "read"
    SKIM = "skim"
    SKIP = "skip"
    BRIEF_SUFFICIENT = "brief_sufficient"


class WatchVerdict(StrEnum):
    WATCH = "watch"
    SKIM = "skim"
    SKIP = "skip"
    TRANSCRIPT_SUFFICIENT = "transcript_sufficient"


class EvidenceLimits(BaseModel):
    source_type: SourceType
    extraction_quality: str
    word_count: int = 0
    notes: list[str] = Field(default_factory=list)


class BriefEntity(BaseModel):
    name: str
    type: str = ""
    description: str = ""


class BriefConcept(BaseModel):
    name: str
    definition: str = ""


class SourceBrief(BaseModel):
    quick_brief: str
    best_next_action: str
    consume_recommendation: str
    key_ideas: list[str] = Field(default_factory=list)
    takeaways: list[str] = Field(default_factory=list)
    important_terms: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    entities: list[BriefEntity] = Field(default_factory=list)
    concepts: list[BriefConcept] = Field(default_factory=list)
    evidence_limits: EvidenceLimits

    watch_verdict: WatchVerdict | Literal[""] = ""
    watch_verdict_reasoning: str = ""
    quick_section_guide: str = ""
    detailed_sections: str = ""
    signal_vs_filler: str = ""

    read_verdict: ReadVerdict | Literal[""] = ""
    why_read_or_skip: str = ""
    key_sections: list[str] = Field(default_factory=list)

    thread_summary: str = ""
    main_claims: list[str] = Field(default_factory=list)
    useful_links_or_references: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_type_specific_fields(self) -> SourceBrief:
        source_type = self.evidence_limits.source_type
        if source_type == SourceType.ARTICLE:
            _require_fields(
                self,
                {
                    "read_verdict": self.read_verdict,
                    "why_read_or_skip": self.why_read_or_skip,
                    "key_sections": self.key_sections,
                },
            )
        elif source_type == SourceType.YOUTUBE:
            _require_fields(
                self,
                {
                    "watch_verdict": self.watch_verdict,
                    "watch_verdict_reasoning": self.watch_verdict_reasoning,
                    "quick_section_guide": self.quick_section_guide,
                    "detailed_sections": self.detailed_sections,
                    "signal_vs_filler": self.signal_vs_filler,
                },
            )
        elif source_type == SourceType.X_THREAD:
            _require_fields(
                self,
                {
                    "thread_summary": self.thread_summary,
                    "main_claims": self.main_claims,
                    "useful_links_or_references": self.useful_links_or_references,
                },
            )
        return self


def validate_source_brief(
    payload: dict[str, Any],
    *,
    source_type: SourceType,
    content: SourceContent,
) -> SourceBrief:
    prepared = dict(payload)
    prepared["evidence_limits"] = compute_evidence_limits(content, source_type=source_type)
    return SourceBrief.model_validate(prepared)


def source_brief_json_schema(source_type: SourceType) -> dict[str, Any]:
    schema = SourceBrief.model_json_schema()
    base_required = [
        "quick_brief",
        "best_next_action",
        "consume_recommendation",
        "key_ideas",
        "takeaways",
        "important_terms",
        "topics",
        "entities",
        "concepts",
    ]
    type_required = {
        SourceType.ARTICLE: ["read_verdict", "why_read_or_skip", "key_sections"],
        SourceType.YOUTUBE: [
            "watch_verdict",
            "watch_verdict_reasoning",
            "quick_section_guide",
            "detailed_sections",
            "signal_vs_filler",
        ],
        SourceType.X_THREAD: [
            "thread_summary",
            "main_claims",
            "useful_links_or_references",
        ],
    }.get(source_type, [])
    schema["required"] = base_required + type_required
    schema["additionalProperties"] = True
    return schema


def compute_evidence_limits(
    content: SourceContent,
    *,
    source_type: SourceType,
) -> EvidenceLimits:
    notes: list[str] = []
    quality = str(content.extraction_quality or "").strip() or "unknown"
    word_count = int(content.word_count or 0)

    if quality in {"partial", "metadata_only", "failed"}:
        notes.append(f"Extraction quality is {quality}.")
    if word_count == 0:
        notes.append("No word count was available for the captured evidence.")
    elif word_count < 300:
        notes.append("Captured evidence is short, so the brief may miss context.")
    if source_type == SourceType.YOUTUBE and "transcript" not in (
        content.extraction_method or ""
    ).lower():
        notes.append("Video evidence may not include a complete transcript.")

    return EvidenceLimits(
        source_type=source_type,
        extraction_quality=quality,
        word_count=word_count,
        notes=notes,
    )


def _require_fields(model: SourceBrief, fields: dict[str, object]) -> None:
    missing = [name for name, value in fields.items() if value in ("", [], None)]
    if missing:
        raise ValueError(
            f"{model.evidence_limits.source_type.value} brief missing required fields: "
            + ", ".join(missing)
        )


SourceBriefValidationError = ValidationError
