"""Shared helpers for readable web extraction ladders."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.source import SourceContent, SourceItem
from app.utils.extraction import (
    WeakExtractionAssessment,
    assess_weak_extraction,
    normalize_whitespace,
    prefer_extraction_candidate,
    score_extraction_quality,
)
from app.utils.hashing import content_hash, url_hash


@dataclass(slots=True)
class ReadableExtractionDraft:
    text: str = ""
    markdown: str = ""
    method: str = ""
    author: str = ""
    published_date: str = ""
    canonical_url: str = ""
    raw_capture_kind: str = ""
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    fallback_chain: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def assess_draft_weakness(
    draft: ReadableExtractionDraft,
    *,
    title: str,
    source_kind: str,
    settings: Any,
) -> WeakExtractionAssessment:
    quality = score_extraction_quality(
        draft.text,
        has_title=bool(title),
        is_metadata_only=(draft.method == "metadata_only"),
    )
    return assess_weak_extraction(
        draft.text,
        title=title,
        extraction_quality=quality.value,
        source_kind=source_kind,
        min_chars=settings.summarize_weak_text_min_chars,
        min_paragraphs=settings.summarize_weak_paragraph_min_count,
        x_snippet_max_chars=settings.summarize_weak_x_snippet_max_chars,
    )


def apply_summarize_candidate(
    draft: ReadableExtractionDraft,
    *,
    summarize_content: SourceContent,
    weakness: WeakExtractionAssessment,
    improved_note: str,
    not_improved_note: str,
    markdown: str = "",
) -> bool:
    current_quality = score_extraction_quality(
        draft.text,
        has_title=True,
        is_metadata_only=(draft.method == "metadata_only"),
    )
    if not prefer_extraction_candidate(
        current_text=draft.text,
        current_quality=current_quality.value,
        candidate_text=summarize_content.cleaned_text,
        candidate_quality=summarize_content.extraction_quality,
    ):
        draft.notes.append(not_improved_note)
        return False

    draft.text = summarize_content.cleaned_text
    draft.markdown = markdown or summarize_content.archived_markdown
    draft.method = summarize_content.extraction_method
    draft.author = summarize_content.author or draft.author
    draft.published_date = summarize_content.published_date or draft.published_date
    draft.canonical_url = summarize_content.canonical_url or draft.canonical_url
    draft.raw_capture_kind = summarize_content.raw_capture_kind or draft.raw_capture_kind
    draft.raw_metadata.update({"summarize": summarize_content.raw_metadata})
    draft.notes.append(improved_note + ": " + ", ".join(weakness.reasons) + ".")
    return True


def apply_metadata_only_fallback(
    draft: ReadableExtractionDraft,
    *,
    text: str,
    note: str,
) -> None:
    draft.fallback_chain.append("metadata_only")
    draft.method = "metadata_only"
    draft.text = text
    draft.markdown = ""
    draft.notes.append(note)


def build_source_content(
    *,
    item: SourceItem,
    raw_text: str,
    draft: ReadableExtractionDraft,
    title: str,
) -> SourceContent:
    cleaned = normalize_whitespace(draft.text)
    quality = score_extraction_quality(
        cleaned,
        has_title=bool(title),
        is_metadata_only=(draft.method == "metadata_only"),
    )
    return SourceContent(
        source=item,
        raw_text=raw_text,
        cleaned_text=cleaned,
        archived_markdown=draft.markdown,
        raw_capture_kind=draft.raw_capture_kind,
        author=draft.author,
        published_date=draft.published_date,
        word_count=len(cleaned.split()) if cleaned else 0,
        extraction_quality=quality.value,
        extraction_method=draft.method,
        extraction_fallback_chain=draft.fallback_chain,
        extraction_notes=" ".join(draft.notes),
        raw_metadata=draft.raw_metadata,
        canonical_url=draft.canonical_url,
        content_hash=content_hash(cleaned) if cleaned else "",
        url_hash=url_hash(item.url),
    )
