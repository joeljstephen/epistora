"""Storage-tier helpers for raw evidence preservation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from app.models.source import SourceContent, SourceType

_HTML_PREFIXES = ("<!doctype html", "<html", "<body", "<head")


@dataclass(frozen=True)
class EvidenceStoragePolicy:
    """Configurable local policy for warm vs cold evidence storage."""

    blob_dir: str = ".system/blobs"
    blob_threshold_bytes: int = 50_000
    blob_preview_chars: int = 4_000


@dataclass(frozen=True)
class BlobArtifact:
    """Cold-storage artifact written under the blob tier."""

    relative_path: str
    absolute_path: Path
    media_type: str
    payload: str
    byte_size: int
    sha256: str


@dataclass(frozen=True)
class PreparedEvidence:
    """Normalized evidence storage decision for a raw capture."""

    content: SourceContent
    storage_tier: str
    blob: BlobArtifact | None = None


def evidence_storage_policy_from_settings(settings: object) -> EvidenceStoragePolicy:
    """Build the storage policy from settings or a settings-like mock."""
    configured_blob_dir_raw = getattr(settings, "evidence_blob_dir", ".system/blobs")
    if not isinstance(configured_blob_dir_raw, (str, Path)):
        configured_blob_dir_raw = ".system/blobs"
    configured_blob_dir = Path(str(configured_blob_dir_raw))

    vault_path_raw = getattr(settings, "vault_path", ".")
    vault_path = vault_path_raw if isinstance(vault_path_raw, Path) else Path(".")
    if configured_blob_dir.is_absolute():
        try:
            configured_blob_dir = configured_blob_dir.relative_to(vault_path)
        except ValueError:
            configured_blob_dir = Path(".system/blobs")

    threshold_raw = getattr(settings, "evidence_blob_threshold_bytes", 50_000)
    threshold = threshold_raw if isinstance(threshold_raw, int) else 50_000

    preview_raw = getattr(settings, "evidence_blob_preview_chars", 4_000)
    preview_chars = preview_raw if isinstance(preview_raw, int) else 4_000

    return EvidenceStoragePolicy(
        blob_dir=str(configured_blob_dir),
        blob_threshold_bytes=threshold,
        blob_preview_chars=preview_chars,
    )


def prepare_evidence_storage(
    *,
    vault_path: Path,
    content: SourceContent,
    slug: str,
    policy: EvidenceStoragePolicy,
) -> PreparedEvidence:
    """Decide whether a capture stays in the warm layer or becomes blob-backed."""
    payload, suffix, media_type = _primary_payload(content)
    byte_size = len(payload.encode("utf-8"))

    metadata = dict(content.raw_metadata)
    metadata["storage_tier"] = "warm"
    metadata.pop("blob_path", None)
    metadata.pop("blob_storage_tier", None)
    metadata.pop("blob_sha256", None)
    metadata.pop("blob_bytes", None)
    metadata.pop("blob_media_type", None)
    metadata.pop("raw_preview_chars", None)
    metadata.pop("raw_preview_text", None)

    if policy.blob_threshold_bytes <= 0 or byte_size < policy.blob_threshold_bytes:
        return PreparedEvidence(
            content=content.model_copy(update={"raw_metadata": metadata}),
            storage_tier="warm",
        )

    relative_path = blob_capture_path(
        vault_path=vault_path,
        source_type=content.source.source_type,
        slug=slug,
        suffix=suffix,
        blob_dir=policy.blob_dir,
    )
    absolute_path = vault_path / relative_path
    sha256 = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    metadata.update(
        {
            "storage_tier": "warm",
            "blob_storage_tier": "cold",
            "blob_path": relative_path,
            "blob_sha256": sha256,
            "blob_bytes": byte_size,
            "blob_media_type": media_type,
            "raw_preview_chars": max(policy.blob_preview_chars, 0),
            "raw_preview_text": _preview_text(content, max(policy.blob_preview_chars, 0)),
        }
    )

    return PreparedEvidence(
        content=content.model_copy(update={"raw_metadata": metadata}),
        storage_tier="warm",
        blob=BlobArtifact(
            relative_path=relative_path,
            absolute_path=absolute_path,
            media_type=media_type,
            payload=payload,
            byte_size=byte_size,
            sha256=sha256,
        ),
    )


def merge_existing_storage_metadata(content: SourceContent, existing_meta: dict) -> SourceContent:
    """Carry forward blob metadata from an existing raw note into a new source note render."""
    metadata = dict(content.raw_metadata)
    for key in (
        "storage_tier",
        "blob_storage_tier",
        "blob_path",
        "blob_sha256",
        "blob_bytes",
        "blob_media_type",
        "raw_preview_chars",
    ):
        value = existing_meta.get(key)
        if value in ("", None):
            continue
        metadata[key] = value
    return content.model_copy(update={"raw_metadata": metadata})


def blob_capture_path(
    *,
    vault_path: Path,
    source_type: SourceType,
    slug: str,
    suffix: str,
    blob_dir: str,
) -> str:
    """Return the relative vault path for a cold blob artifact."""
    del vault_path
    resolved_blob_dir = Path(blob_dir)
    return str(resolved_blob_dir / _blob_subdir(source_type) / slug / f"primary{suffix}")


def _blob_subdir(source_type: SourceType) -> str:
    return {
        SourceType.ARTICLE: "articles",
        SourceType.YOUTUBE: "videos",
        SourceType.X_THREAD: "threads",
        SourceType.PDF: "pdfs",
        SourceType.GENERIC: "misc",
        SourceType.DERIVED_WORK: "derived",
    }[source_type]


def _primary_payload(content: SourceContent) -> tuple[str, str, str]:
    archived = content.archived_markdown.strip()
    if archived:
        return archived + "\n", ".md", "text/markdown"

    raw_text = content.raw_text.strip()
    if raw_text:
        lowered = raw_text[:200].strip().lower()
        if any(lowered.startswith(prefix) for prefix in _HTML_PREFIXES):
            return raw_text + ("\n" if not raw_text.endswith("\n") else ""), ".html", "text/html"
        return raw_text + ("\n" if not raw_text.endswith("\n") else ""), ".txt", "text/plain"

    cleaned = content.cleaned_text.strip()
    if cleaned:
        return cleaned + "\n", ".txt", "text/plain"

    return "_No raw text captured._\n", ".txt", "text/plain"


def _preview_text(content: SourceContent, preview_chars: int) -> str:
    source = (
        content.cleaned_text.strip()
        or content.archived_markdown.strip()
        or content.raw_text.strip()
        or "_No readable preview available._"
    )
    if preview_chars <= 0 or len(source) <= preview_chars:
        return source
    clipped = source[:preview_chars].rstrip()
    return (
        clipped
        + "\n\n[Preview truncated. Open the blob path above for the full "
        + "preserved evidence.]"
    )
