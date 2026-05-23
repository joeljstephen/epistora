from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

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
    summary: str = ""
    five_minute_read: str = ""
    detailed_reading_note: str = ""
    best_next_action: str
    consume_recommendation: str
    key_ideas: list[str] = Field(default_factory=list)
    detailed_outline: str = ""
    important_examples: list[str] = Field(default_factory=list)
    takeaways: list[str] = Field(default_factory=list)
    notable_quotes: list[str] = Field(default_factory=list)
    best_for: list[str] = Field(default_factory=list)
    why_it_matters: str = ""
    open_questions: list[str] = Field(default_factory=list)
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

    @field_validator(
        "key_ideas",
        "important_examples",
        "takeaways",
        "notable_quotes",
        "best_for",
        "important_terms",
        "open_questions",
        "topics",
        "key_sections",
        "main_claims",
        "useful_links_or_references",
        mode="before",
    )
    @classmethod
    def _coerce_string_list(cls, value: object) -> list[str]:
        if value in (None, ""):
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return _string_to_list(value)
        return [str(value).strip()] if str(value).strip() else []

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
    if "takeaways" not in prepared and "actionable_takeaways" in prepared:
        prepared["takeaways"] = prepared["actionable_takeaways"]
    prepared["evidence_limits"] = compute_evidence_limits(content, source_type=source_type)
    return SourceBrief.model_validate(prepared)


def source_brief_json_schema(source_type: SourceType) -> dict[str, Any]:
    schema = SourceBrief.model_json_schema()
    base_required = [
        "quick_brief",
        "summary",
        "five_minute_read",
        "detailed_reading_note",
        "best_next_action",
        "consume_recommendation",
        "key_ideas",
        "detailed_outline",
        "important_examples",
        "takeaways",
        "notable_quotes",
        "best_for",
        "why_it_matters",
        "open_questions",
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


def source_brief_to_analysis(brief: SourceBrief) -> dict[str, object]:
    evidence_limit_notes = "\n".join(f"- {note}" for note in brief.evidence_limits.notes)
    detailed_outline = brief.detailed_outline or evidence_limit_notes
    summary = brief.summary or brief.quick_brief
    detailed_reading_note = brief.detailed_reading_note or summary
    five_minute_read = brief.five_minute_read or summary
    return {
        "_brief_status": "ready",
        "quick_brief": brief.quick_brief,
        "summary": summary,
        "five_minute_read": five_minute_read,
        "detailed_reading_note": detailed_reading_note,
        "best_next_action": brief.best_next_action,
        "watch_verdict": str(brief.watch_verdict or ""),
        "watch_verdict_reasoning": brief.watch_verdict_reasoning,
        "quick_section_guide": brief.quick_section_guide,
        "detailed_sections": brief.detailed_sections,
        "signal_vs_filler": brief.signal_vs_filler,
        "important_terms": list(brief.important_terms),
        "key_ideas": list(brief.key_ideas),
        "detailed_outline": detailed_outline,
        "important_examples": list(brief.important_examples),
        "actionable_takeaways": list(brief.takeaways),
        "takeaways": list(brief.takeaways),
        "notable_quotes": list(brief.notable_quotes),
        "best_for": list(brief.best_for),
        "consume_recommendation": _consume_recommendation(brief),
        "why_it_matters": brief.why_it_matters
        or brief.why_read_or_skip
        or brief.thread_summary
        or brief.quick_brief,
        "open_questions": list(brief.open_questions),
        "topics": list(brief.topics),
        "entities": [entity.model_dump() for entity in brief.entities],
        "concepts": [concept.model_dump() for concept in brief.concepts],
    }


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


def _consume_recommendation(brief: SourceBrief) -> str:
    if brief.read_verdict:
        return f"{brief.read_verdict}: {brief.consume_recommendation}"
    if brief.watch_verdict:
        return f"{brief.watch_verdict}: {brief.consume_recommendation}"
    return brief.consume_recommendation


def _string_to_list(value: str) -> list[str]:
    items: list[str] = []
    for line in value.splitlines():
        cleaned = line.strip().lstrip("-*•→ ").strip()
        if cleaned:
            items.append(cleaned)
    if items:
        return items
    return [value.strip()] if value.strip() else []


SourceBriefValidationError = ValidationError
