"""summarize.sh CLI wrapper and SourceContent normalization helpers."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any

from app.config import Settings, get_settings
from app.models.source import ExtractionQuality, SourceContent, SourceItem
from app.utils.extraction import normalize_whitespace, score_extraction_quality
from app.utils.hashing import content_hash, url_hash

logger = logging.getLogger(__name__)

_AUTHOR_KEYS = (
    "author",
    "author_name",
    "authorName",
    "creator",
    "channel",
    "channelName",
    "channelTitle",
    "publisher",
)
_DATE_KEYS = (
    "published",
    "published_at",
    "publishedAt",
    "published_date",
    "publishedDate",
    "publishedTime",
    "uploadDate",
    "date",
)


@dataclass(slots=True)
class SummarizeResult:
    success: bool
    raw_output: str = ""
    cleaned_text: str = ""
    archived_markdown: str = ""
    title: str = ""
    author: str = ""
    published_date: str = ""
    canonical_url: str = ""
    extraction_method: str = ""
    provider_notes: str = ""
    quality_hint: str = ""
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    stderr: str = ""
    returncode: int | None = None


def is_available(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    if not settings.summarize_enabled:
        return False
    return shutil.which(settings.summarize_binary) is not None


async def extract_url(
    url: str,
    *,
    source_kind: str,
    prefer_markdown: bool = True,
    settings: Settings | None = None,
) -> SummarizeResult:
    settings = settings or get_settings()
    args = _build_command(
        url,
        source_kind=source_kind,
        prefer_markdown=prefer_markdown,
        settings=settings,
    )
    return await _run_command(args, url=url, source_kind=source_kind, settings=settings)


async def extract_media(
    url: str,
    *,
    prefer_markdown: bool = True,
    settings: Settings | None = None,
) -> SummarizeResult:
    settings = settings or get_settings()
    args = _build_command(
        url,
        source_kind="media",
        prefer_markdown=prefer_markdown,
        settings=settings,
    )
    return await _run_command(args, url=url, source_kind="media", settings=settings)


def summarize_result_to_source_content(
    item: SourceItem,
    result: SummarizeResult,
    *,
    raw_capture_kind: str,
    fallback_chain: list[str],
    notes_prefix: str = "",
) -> SourceContent:
    title = item.title or result.title or item.url
    item.title = title

    cleaned_text = normalize_whitespace(result.cleaned_text)
    archived_markdown = result.archived_markdown.strip()
    quality = result.quality_hint or score_extraction_quality(
        cleaned_text,
        has_title=bool(title),
        is_metadata_only=not cleaned_text,
    ).value

    notes = [notes_prefix.strip(), result.provider_notes.strip()]
    if not cleaned_text:
        notes.append("summarize returned no extractable body text.")

    raw_metadata = dict(result.raw_metadata)
    raw_metadata.setdefault("provider", "summarize")
    raw_metadata.setdefault("summarize_success", result.success)
    raw_metadata.setdefault("summarize_returncode", result.returncode)

    return SourceContent(
        source=item,
        raw_text=result.raw_output.strip(),
        cleaned_text=cleaned_text,
        archived_markdown=archived_markdown,
        raw_capture_kind=raw_capture_kind,
        author=result.author,
        published_date=result.published_date,
        word_count=len(cleaned_text.split()) if cleaned_text else 0,
        extraction_quality=quality,
        extraction_method=result.extraction_method or "summarize_cli",
        extraction_fallback_chain=fallback_chain,
        extraction_notes=" ".join(part for part in notes if part),
        raw_metadata=raw_metadata,
        canonical_url=result.canonical_url or item.url,
        content_hash=content_hash(cleaned_text) if cleaned_text else "",
        url_hash=url_hash(item.url),
    )


def _build_command(
    url: str,
    *,
    source_kind: str,
    prefer_markdown: bool,
    settings: Settings,
) -> list[str]:
    args = [
        settings.summarize_binary,
        url,
        "--extract",
        "--json",
        "--plain",
        "--timeout",
        f"{max(settings.summarize_timeout_seconds, 1)}s",
        "--format",
        "md" if prefer_markdown else "text",
    ]

    if source_kind == "youtube":
        args.extend(["--video-mode", "transcript", "--youtube", "auto"])
    elif source_kind in {"x", "article", "generic"}:
        args.extend(["--firecrawl", "auto"])

    return args


async def _run_command(
    args: list[str],
    *,
    url: str,
    source_kind: str,
    settings: Settings,
) -> SummarizeResult:
    if not settings.summarize_enabled:
        return SummarizeResult(
            success=False,
            extraction_method="summarize_cli",
            provider_notes="summarize integration disabled.",
        )
    if not is_available(settings):
        return SummarizeResult(
            success=False,
            extraction_method="summarize_cli",
            provider_notes=f"summarize binary not found: {settings.summarize_binary}",
        )

    try:
        completed = await asyncio.to_thread(
            subprocess.run,
            args,
            capture_output=True,
            text=True,
            timeout=max(settings.summarize_timeout_seconds, 1),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return SummarizeResult(
            success=False,
            extraction_method="summarize_cli",
            provider_notes=(
                f"summarize timed out after {max(settings.summarize_timeout_seconds, 1)} seconds."
            ),
        )
    except Exception as exc:
        logger.warning("summarize invocation failed for %s: %s", url, exc)
        return SummarizeResult(
            success=False,
            extraction_method="summarize_cli",
            provider_notes=f"summarize invocation failed: {exc}",
        )

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    if completed.returncode != 0:
        detail = normalize_whitespace(stderr or stdout) or "non-zero exit"
        return SummarizeResult(
            success=False,
            raw_output=stdout,
            stderr=stderr,
            returncode=completed.returncode,
            extraction_method="summarize_cli",
            provider_notes=f"summarize exited with code {completed.returncode}: {detail}",
        )

    payload = _parse_json_output(stdout)
    if not payload:
        return SummarizeResult(
            success=False,
            raw_output=stdout,
            stderr=stderr,
            returncode=completed.returncode,
            extraction_method="summarize_cli",
            provider_notes="summarize returned invalid JSON output.",
        )

    extracted = payload.get("extracted")
    if not isinstance(extracted, dict):
        return SummarizeResult(
            success=False,
            raw_output=stdout,
            stderr=stderr,
            returncode=completed.returncode,
            extraction_method="summarize_cli",
            provider_notes="summarize JSON missing extracted payload.",
            raw_metadata={"payload": payload},
        )

    content = _as_text(extracted.get("content"))
    archived_markdown = (
        content if _looks_like_markdown(content) else _plain_text_to_markdown(content)
    )
    cleaned_text = _markdown_to_text(content) if _looks_like_markdown(content) else content
    cleaned_text = normalize_whitespace(cleaned_text)

    raw_metadata = {
        "payload": payload,
        "site_name": _as_text(extracted.get("siteName")),
        "description": _as_text(extracted.get("description")),
        "transcript_source": _as_text(extracted.get("transcriptSource")),
        "transcript_word_count": _as_int(extracted.get("transcriptWordCount")),
        "media_duration_seconds": _as_int(extracted.get("mediaDurationSeconds")),
        "diagnostics": extracted.get("diagnostics", {}),
    }

    return SummarizeResult(
        success=True,
        raw_output=stdout,
        cleaned_text=cleaned_text,
        archived_markdown=archived_markdown.strip(),
        title=_as_text(extracted.get("title")),
        author=_extract_nested_text(extracted, _AUTHOR_KEYS),
        published_date=_extract_nested_text(extracted, _DATE_KEYS),
        canonical_url=_as_text(extracted.get("url")) or url,
        extraction_method="summarize_cli",
        provider_notes=_build_provider_notes(
            source_kind=source_kind,
            extracted=extracted,
            stderr=stderr,
        ),
        quality_hint=_derive_quality_hint(source_kind=source_kind, extracted=extracted),
        raw_metadata=raw_metadata,
        stderr=stderr,
        returncode=completed.returncode,
    )


def _parse_json_output(stdout: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(stdout)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}\s*$", stdout, flags=re.S)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        return None


def _build_provider_notes(
    *,
    source_kind: str,
    extracted: dict[str, Any],
    stderr: str,
) -> str:
    notes: list[str] = []
    transcript_source = _as_text(extracted.get("transcriptSource"))
    if transcript_source:
        notes.append(f"Transcript source: {transcript_source}.")
    strategy = _extract_nested_text(extracted.get("diagnostics", {}), ("strategy",))
    if strategy:
        notes.append(f"Strategy: {strategy}.")
    if stderr.strip():
        notes.append(f"stderr: {normalize_whitespace(stderr)[:240]}")
    if source_kind == "youtube" and not transcript_source:
        notes.append("summarize returned video extraction without an explicit transcript source.")
    return " ".join(notes)


def _derive_quality_hint(*, source_kind: str, extracted: dict[str, Any]) -> str:
    content = normalize_whitespace(_markdown_to_text(_as_text(extracted.get("content"))))
    transcript_source = _as_text(extracted.get("transcriptSource"))
    if not content:
        return ExtractionQuality.METADATA_ONLY.value

    quality = score_extraction_quality(
        content,
        has_title=bool(_as_text(extracted.get("title"))),
        is_metadata_only=False,
        is_auto_caption=source_kind == "youtube" and transcript_source in {"auto", "web"},
    )
    return quality.value


def _extract_nested_text(value: Any, keys: tuple[str, ...]) -> str:
    if isinstance(value, dict):
        for key in keys:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return normalize_whitespace(candidate)
        for nested in value.values():
            found = _extract_nested_text(nested, keys)
            if found:
                return found
    if isinstance(value, list):
        for nested in value:
            found = _extract_nested_text(nested, keys)
            if found:
                return found
    return ""


def _looks_like_markdown(text: str) -> bool:
    return bool(
        re.search(r"(^#|\n#|\[.+?\]\(.+?\)|^\s*[-*]\s+)", text, flags=re.M)
        or "```" in text
    )


def _markdown_to_text(text: str) -> str:
    stripped = re.sub(r"```.*?```", " ", text, flags=re.S)
    stripped = re.sub(r"`([^`]+)`", r"\1", stripped)
    stripped = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", stripped)
    stripped = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", stripped)
    stripped = re.sub(r"^#{1,6}\s*", "", stripped, flags=re.M)
    stripped = re.sub(r"^\s*[-*]\s+", "", stripped, flags=re.M)
    stripped = re.sub(r"^\s*>\s?", "", stripped, flags=re.M)
    stripped = stripped.replace("---", "\n")
    return normalize_whitespace(stripped)


def _plain_text_to_markdown(text: str) -> str:
    cleaned = normalize_whitespace(text)
    if not cleaned:
        return ""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", cleaned) if p.strip()]
    if not paragraphs:
        return cleaned
    return "\n\n".join(paragraphs)


def _as_text(value: Any) -> str:
    return normalize_whitespace(str(value)) if isinstance(value, str) and value.strip() else ""


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None
