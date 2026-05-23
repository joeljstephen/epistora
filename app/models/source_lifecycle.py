"""Source lifecycle transitions and display-state rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.models.db import (
    CatalogSource,
    SourceBriefStatus,
    SourceContentStatus,
    SourceDeepStatus,
    SourceFailureStatus,
    SourceMetadataStatus,
    SourceOutputStatus,
)


@dataclass(frozen=True)
class SourceLifecycleTransition:
    """A named catalog lifecycle transition."""

    name: str
    updates: dict[str, str | None] = field(default_factory=dict)


class SourceLifecycleRepository(Protocol):
    def update_lifecycle(
        self,
        source_uid: str,
        *,
        metadata_status: str | None = None,
        content_status: str | None = None,
        brief_status: str | None = None,
        deep_status: str | None = None,
        output_status: str | None = None,
        failure_status: str | None = None,
        last_failure_reason: str | None = None,
        canonical_url: str | None = None,
        content_hash: str | None = None,
        title: str | None = None,
        source_type: str | None = None,
    ) -> CatalogSource: ...


def apply_transition(
    repo: SourceLifecycleRepository,
    source_uid: str,
    transition: SourceLifecycleTransition,
) -> CatalogSource:
    return repo.update_lifecycle(source_uid, **transition.updates)


def extracted_content_imported() -> SourceLifecycleTransition:
    return SourceLifecycleTransition(
        name="extracted_content_imported",
        updates={
            "metadata_status": SourceMetadataStatus.CAPTURED.value,
            "content_status": SourceContentStatus.AVAILABLE.value,
            "brief_status": SourceBriefStatus.NOT_STARTED.value,
            "output_status": SourceOutputStatus.NOT_PUBLISHED.value,
            "failure_status": SourceFailureStatus.NONE.value,
            "last_failure_reason": "",
        },
    )


def capture_published(
    *,
    content_hash: str | None = None,
    title: str | None = None,
    source_type: str | None = None,
) -> SourceLifecycleTransition:
    return SourceLifecycleTransition(
        name="capture_published",
        updates={
            "metadata_status": SourceMetadataStatus.CAPTURED.value,
            "content_status": SourceContentStatus.AVAILABLE.value,
            "brief_status": SourceBriefStatus.PARTIAL.value,
            "output_status": SourceOutputStatus.PUBLISHED.value,
            "failure_status": SourceFailureStatus.NONE.value,
            "last_failure_reason": "",
            "content_hash": content_hash,
            "title": title,
            "source_type": source_type,
        },
    )


def brief_published(*, content_hash: str | None = None) -> SourceLifecycleTransition:
    return SourceLifecycleTransition(
        name="brief_published",
        updates={
            "metadata_status": SourceMetadataStatus.CAPTURED.value,
            "content_status": SourceContentStatus.AVAILABLE.value,
            "brief_status": SourceBriefStatus.READY.value,
            "output_status": SourceOutputStatus.PUBLISHED.value,
            "failure_status": SourceFailureStatus.NONE.value,
            "last_failure_reason": "",
            "content_hash": content_hash,
        },
    )


def deep_compiled(
    *,
    content_hash: str | None = None,
    title: str | None = None,
    source_type: str | None = None,
) -> SourceLifecycleTransition:
    transition = brief_published(content_hash=content_hash).updates | {
        "deep_status": SourceDeepStatus.COMPILED.value,
        "title": title,
        "source_type": source_type,
    }
    return SourceLifecycleTransition(name="deep_compiled", updates=transition)


def duplicate_published() -> SourceLifecycleTransition:
    return SourceLifecycleTransition(
        name="duplicate_published",
        updates={
            "metadata_status": SourceMetadataStatus.CAPTURED.value,
            "content_status": SourceContentStatus.AVAILABLE.value,
            "brief_status": SourceBriefStatus.READY.value,
            "output_status": SourceOutputStatus.PUBLISHED.value,
            "failure_status": SourceFailureStatus.NONE.value,
            "last_failure_reason": "",
        },
    )


def partial_failure(error: str) -> SourceLifecycleTransition:
    return SourceLifecycleTransition(
        name="partial_failure",
        updates={
            "failure_status": SourceFailureStatus.PARTIAL.value,
            "last_failure_reason": error[:500],
        },
    )


def hard_failure(error: str) -> SourceLifecycleTransition:
    return SourceLifecycleTransition(
        name="hard_failure",
        updates={
            "failure_status": SourceFailureStatus.FAILED.value,
            "last_failure_reason": error[:500],
        },
    )


def brief_failed(error: str) -> SourceLifecycleTransition:
    return SourceLifecycleTransition(
        name="brief_failed",
        updates={
            "brief_status": SourceBriefStatus.FAILED.value,
            "failure_status": SourceFailureStatus.FAILED.value,
            "last_failure_reason": error[:500],
        },
    )


def import_failed(error: str) -> SourceLifecycleTransition:
    return SourceLifecycleTransition(
        name="import_failed",
        updates={
            "metadata_status": SourceMetadataStatus.METADATA_ONLY.value,
            "content_status": SourceContentStatus.FAILED.value,
            "brief_status": SourceBriefStatus.NOT_STARTED.value,
            "output_status": SourceOutputStatus.NOT_PUBLISHED.value,
            "failure_status": SourceFailureStatus.FAILED.value,
            "last_failure_reason": error[:500],
        },
    )


def derive_display_state(source: CatalogSource) -> str:
    if source.failure_status == SourceFailureStatus.FAILED.value:
        return "failed"
    if source.failure_status == SourceFailureStatus.PARTIAL.value:
        return "failed_partial"
    if source.deep_status == SourceDeepStatus.COMPILED.value:
        return "deep_compiled"
    if source.brief_status == SourceBriefStatus.READY.value:
        return "brief_ready"
    if source.content_status == SourceContentStatus.AVAILABLE.value:
        return "content_available"
    return "metadata_only"


def display_state_clause(display_state: str) -> tuple[str, list[str]]:
    if display_state == "metadata_only":
        return (
            "s.metadata_status = ? AND s.content_status = ? AND s.failure_status = ?"
            " AND s.deep_status != ? AND s.brief_status != ?",
            [
                SourceMetadataStatus.METADATA_ONLY.value,
                SourceContentStatus.NOT_FETCHED.value,
                SourceFailureStatus.NONE.value,
                SourceDeepStatus.COMPILED.value,
                SourceBriefStatus.READY.value,
            ],
        )
    if display_state == "content_available":
        return (
            "s.content_status = ? AND s.brief_status NOT IN (?, ?) AND s.deep_status != ?"
            " AND s.failure_status = ?",
            [
                SourceContentStatus.AVAILABLE.value,
                SourceBriefStatus.READY.value,
                SourceBriefStatus.PARTIAL.value,
                SourceDeepStatus.COMPILED.value,
                SourceFailureStatus.NONE.value,
            ],
        )
    if display_state == "brief_ready":
        return (
            "s.brief_status = ? AND s.deep_status != ? AND s.failure_status = ?",
            [
                SourceBriefStatus.READY.value,
                SourceDeepStatus.COMPILED.value,
                SourceFailureStatus.NONE.value,
            ],
        )
    if display_state == "deep_compiled":
        return ("s.deep_status = ? AND s.failure_status = ?", [
            SourceDeepStatus.COMPILED.value,
            SourceFailureStatus.NONE.value,
        ])
    if display_state == "failed":
        return ("s.failure_status = ?", [SourceFailureStatus.FAILED.value])
    if display_state == "failed_partial":
        return ("s.failure_status = ?", [SourceFailureStatus.PARTIAL.value])
    return ("", [])
