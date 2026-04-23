"""YouTube video extraction with multi-tier fallback chain.

Fallback order:
1. youtube-transcript-api (prefer manual English -> auto English -> any)
2. yt-dlp subtitle-only fallback
3. metadata/noembed fallback
4. Optional local ASR hook (extension point, disabled)
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings
from app.connectors.fetchers.summarize_cli import (
    extract_url as summarize_extract_url,
)
from app.connectors.fetchers.summarize_cli import (
    is_available as summarize_is_available,
)
from app.connectors.fetchers.summarize_cli import (
    summarize_result_to_source_content,
)
from app.models.source import ExtractionQuality, SourceContent, SourceItem
from app.utils.extraction import (
    assess_weak_extraction,
    normalize_whitespace,
    prefer_extraction_candidate,
    truncate_text,
)
from app.utils.hashing import content_hash, url_hash

logger = logging.getLogger(__name__)

_VIDEO_ID_RE = re.compile(r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([a-zA-Z0-9_-]{11})")
_TIMESTAMP_RE = re.compile(
    r"(?P<hours>\d{2}:)?(?P<minutes>\d{2}):(?P<seconds>\d{2})(?:\.\d+)?"
)


def _looks_like_url(text: str) -> bool:
    if not text:
        return False
    stripped = text.strip()
    return stripped.startswith("http://") or stripped.startswith("https://")


def _extract_video_id(url: str) -> str | None:
    m = _VIDEO_ID_RE.search(url)
    return m.group(1) if m else None


async def fetch_youtube(item: SourceItem) -> SourceContent:
    """Fetch YouTube video transcript and metadata with fallback chain."""
    settings = get_settings()
    video_id = _extract_video_id(item.url)

    if not video_id:
        return SourceContent(
            source=item,
            extraction_quality="failed",
            extraction_method="none",
            extraction_fallback_chain=["video_id_parse_failed"],
            extraction_notes="Could not extract video ID from URL.",
            raw_capture_kind="youtube_metadata_note",
            url_hash=url_hash(item.url),
        )

    fallback_chain: list[str] = []
    notes_parts: list[str] = []
    transcript_text = ""
    method = ""
    is_auto_caption = False
    caption_type = "none"
    summarize_content: SourceContent | None = None

    if (
        getattr(settings, "summarize_use_for_youtube_primary", False)
        and summarize_is_available(settings)
    ):
        fallback_chain.append("summarize_cli")
        summarize_result = await summarize_extract_url(
            item.url,
            source_kind="youtube",
            prefer_markdown=getattr(settings, "summarize_prefer_markdown", True),
            settings=settings,
        )
        if summarize_result.success:
            summarize_content = summarize_result_to_source_content(
                item,
                summarize_result,
                raw_capture_kind="summarize_youtube_extract",
                fallback_chain=fallback_chain.copy(),
                notes_prefix="summarize used as primary YouTube extractor.",
            )
            summarize_weakness = assess_weak_extraction(
                summarize_content.cleaned_text,
                title=summarize_content.source.title,
                extraction_quality=summarize_content.extraction_quality,
                source_kind="youtube",
                min_chars=settings.summarize_weak_text_min_chars,
                min_paragraphs=settings.summarize_weak_paragraph_min_count,
                x_snippet_max_chars=settings.summarize_weak_x_snippet_max_chars,
            )
            if not summarize_weakness.is_weak:
                transcript_text = summarize_content.cleaned_text
                method = summarize_content.extraction_method
                caption_type = (
                    str(summarize_content.raw_metadata.get("transcript_source") or "summarize")
                    .strip()
                    .lower()
                )
                notes_parts.append("summarize primary extraction succeeded.")
            else:
                notes_parts.append(
                    "summarize returned weak YouTube output: "
                    + ", ".join(summarize_weakness.reasons)
                    + "."
                )
        else:
            notes_parts.append(
                f"summarize primary extraction failed: {summarize_result.provider_notes}"
            )

    if not transcript_text:
        transcript_text, method, is_auto_caption, note = await _try_transcript_api(video_id)
        fallback_chain.append("youtube_transcript_api")
        if note:
            notes_parts.append(note)

        if (
            not transcript_text
            and settings.youtube_use_ytdlp_fallback
            and shutil.which("yt-dlp")
        ):
            transcript_text, method, is_auto_caption, note = _try_ytdlp(
                video_id, timeout=settings.youtube_fetch_timeout_seconds
            )
            fallback_chain.append("yt_dlp")
            if note:
                notes_parts.append(note)

    title, channel, description, duration = await _fetch_video_metadata(
        video_id,
        item.title,
        timeout=settings.youtube_fetch_timeout_seconds,
    )

    if summarize_content and (
        not transcript_text
        or prefer_extraction_candidate(
            current_text=transcript_text,
            current_quality=(
                ExtractionQuality.MOSTLY_FULL.value
                if transcript_text and is_auto_caption
                else (
                    ExtractionQuality.FULL.value
                    if transcript_text
                    else ExtractionQuality.METADATA_ONLY.value
                )
            ),
            candidate_text=summarize_content.cleaned_text,
            candidate_quality=summarize_content.extraction_quality,
        )
    ):
        transcript_text = summarize_content.cleaned_text
        method = summarize_content.extraction_method
        caption_type = (
            str(summarize_content.raw_metadata.get("transcript_source") or "summarize")
            .strip()
            .lower()
        )
        notes_parts.append("Kept summarize output after comparing with local YouTube fallbacks.")
        is_auto_caption = caption_type == "auto"

    if not transcript_text:
        fallback_chain.append("metadata_only")
        method = "metadata_only"
        notes_parts.append("Transcript unavailable from all sources; metadata-only ingest.")

    transcript_text = normalize_whitespace(transcript_text)

    max_chars = settings.youtube_transcript_max_chars
    if transcript_text and max_chars > 0:
        transcript_text, was_truncated = truncate_text(transcript_text, max_chars)
        if was_truncated:
            notes_parts.append(f"Transcript truncated to {max_chars} chars.")

    if _looks_like_url(item.title):
        item.title = (
            title
            or (summarize_content.source.title if summarize_content else "")
            or item.title
        )
    else:
        item.title = (
            item.title
            or (summarize_content.source.title if summarize_content else "")
            or title
            or f"YouTube Video {video_id}"
        )
    channel = channel or (summarize_content.author if summarize_content else "")

    if transcript_text and caption_type == "none":
        caption_type = "auto" if is_auto_caption else "manual"

    if transcript_text:
        if summarize_content and method == "summarize_cli":
            quality = ExtractionQuality(summarize_content.extraction_quality)
        else:
            quality = ExtractionQuality.MOSTLY_FULL if is_auto_caption else ExtractionQuality.FULL
        cleaned_text = transcript_text
    else:
        quality = ExtractionQuality.METADATA_ONLY
        cleaned_text = normalize_whitespace(description or "")

    archived_markdown = _build_youtube_archive_markdown(
        title=item.title,
        source_url=item.url,
        channel=channel,
        duration=duration,
        description=description,
        transcript_text=transcript_text,
        caption_type=caption_type,
        extraction_method=method or "metadata_only",
        extraction_quality=quality.value,
    )

    raw_text_lines = [
        f"Video ID: {video_id}",
        f"Title: {item.title}",
        f"Channel: {channel}",
    ]
    if duration:
        raw_text_lines.append(f"Duration: {duration}")
    if description:
        raw_text_lines.append(f"Description: {description[:1500]}")
    if transcript_text:
        raw_text_lines.extend(["", transcript_text])

    raw_metadata: dict[str, Any] = {
        "video_id": video_id,
        "channel": channel,
        "duration": duration,
        "description": description[:2000] if description else "",
        "transcript_available": bool(transcript_text),
        "caption_type": caption_type,
        "transcript_source": method or "metadata_only",
        "transcript_quality": _transcript_quality_label(
            transcript_available=bool(transcript_text),
            is_auto_caption=is_auto_caption,
            quality=quality.value,
        ),
        "transcript_section_count": len(_transcript_sections(transcript_text)),
        "transcript_word_count": len(transcript_text.split()) if transcript_text else 0,
    }
    if summarize_content:
        raw_metadata["summarize"] = summarize_content.raw_metadata

    return SourceContent(
        source=item,
        raw_text="\n".join(raw_text_lines).strip(),
        cleaned_text=cleaned_text,
        archived_markdown=archived_markdown,
        raw_capture_kind=(
            summarize_content.raw_capture_kind
            if summarize_content and method == "summarize_cli"
            else ("youtube_transcript" if transcript_text else "youtube_metadata_note")
        ),
        author=channel or (summarize_content.author if summarize_content else ""),
        word_count=len(transcript_text.split()) if transcript_text else 0,
        extraction_quality=quality.value,
        extraction_method=method or "metadata_only",
        extraction_fallback_chain=fallback_chain,
        extraction_notes=" ".join(notes_parts),
        raw_metadata=raw_metadata,
        canonical_url=f"https://www.youtube.com/watch?v={video_id}",
        content_hash=content_hash(transcript_text) if transcript_text else "",
        url_hash=url_hash(item.url),
    )


async def _try_transcript_api(
    video_id: str,
) -> tuple[str, str, bool, str]:
    """Attempt youtube-transcript-api. Returns (text, method, is_auto, note)."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        ytt_api = YouTubeTranscriptApi()
        transcript_list = ytt_api.list(video_id)

        selected = None
        is_auto = False

        manual_transcripts = [t for t in transcript_list if not t.is_generated]
        auto_transcripts = [t for t in transcript_list if t.is_generated]

        for transcript in manual_transcripts:
            if transcript.language_code.startswith("en"):
                selected = transcript
                break
        if not selected:
            for transcript in auto_transcripts:
                if transcript.language_code.startswith("en"):
                    selected = transcript
                    is_auto = True
                    break
        if not selected and manual_transcripts:
            selected = manual_transcripts[0]
        if not selected and auto_transcripts:
            selected = auto_transcripts[0]
            is_auto = True

        if selected:
            snippets = selected.fetch()
            text = _transcript_snippets_to_sectioned_text(snippets)
            note_parts: list[str] = []
            if is_auto:
                note_parts.append("Using auto-generated captions (may contain errors).")
            if not selected.language_code.startswith("en"):
                note_parts.append(f"Transcript language: {selected.language_code}.")
            return text, "youtube_transcript_api", is_auto, " ".join(note_parts)

        return "", "", False, "No transcripts found via transcript API."

    except Exception as exc:
        logger.debug("youtube-transcript-api failed for %s: %s", video_id, exc)
        return "", "", False, f"Transcript API failed: {exc}"


def _try_ytdlp(video_id: str, *, timeout: int) -> tuple[str, str, bool, str]:
    """Attempt yt-dlp subtitle-only extraction. Returns (text, method, is_auto, note)."""
    url = f"https://www.youtube.com/watch?v={video_id}"

    with tempfile.TemporaryDirectory() as tmpdir:
        for sub_flag in ["--write-subs", "--write-auto-subs"]:
            is_auto = sub_flag == "--write-auto-subs"
            try:
                subprocess.run(
                    [
                        "yt-dlp",
                        "--skip-download",
                        sub_flag,
                        "--sub-lang",
                        "en",
                        "--sub-format",
                        "vtt",
                        "--output",
                        f"{tmpdir}/%(id)s.%(ext)s",
                        url,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=max(timeout, 1),
                )

                vtt_files = list(Path(tmpdir).glob("*.vtt"))
                if vtt_files:
                    text = _parse_vtt(vtt_files[0].read_text(encoding="utf-8"))
                    if text:
                        note = "auto-caption" if is_auto else "manual subtitle"
                        return text, "yt_dlp", is_auto, f"Extracted via yt-dlp ({note})."
            except subprocess.TimeoutExpired:
                return "", "", False, "yt-dlp timed out."
            except Exception as exc:
                logger.debug("yt-dlp attempt failed: %s", exc)
                continue

    return "", "", False, "yt-dlp found no subtitles."


def _parse_vtt(vtt_content: str) -> str:
    """Parse WebVTT content into a sectioned transcript."""
    segments = _parse_vtt_segments(vtt_content)
    return _transcript_segments_to_sectioned_text(segments)


def _parse_vtt_segments(vtt_content: str) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    current_timing: tuple[float, float] | None = None

    for raw_line in vtt_content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("WEBVTT") or line.startswith("NOTE"):
            continue
        if re.match(r"^\d+$", line):
            continue
        if "-->" in line:
            parts = [part.strip() for part in line.split("-->")]
            if len(parts) == 2:
                current_timing = (_timestamp_to_seconds(parts[0]), _timestamp_to_seconds(parts[1]))
            continue

        clean = re.sub(r"<[^>]+>", "", line).strip()
        if not clean or clean == "[Music]":
            continue
        clean = _normalize_transcript_line(clean)
        if not clean:
            continue

        start = current_timing[0] if current_timing else 0.0
        duration = (current_timing[1] - current_timing[0]) if current_timing else 0.0
        _append_transcript_segment(segments, start, duration, clean)

    return segments


def _transcript_snippets_to_sectioned_text(snippets: Any) -> str:
    segments: list[dict[str, Any]] = []

    for snippet in snippets:
        text = _snippet_value(snippet, "text")
        if not text:
            continue
        clean = _normalize_transcript_line(str(text))
        if not clean or clean == "[Music]":
            continue
        start = float(_snippet_value(snippet, "start", default=0.0) or 0.0)
        duration = float(_snippet_value(snippet, "duration", default=0.0) or 0.0)
        _append_transcript_segment(segments, start, duration, clean)

    return _transcript_segments_to_sectioned_text(segments)


def _snippet_value(snippet: Any, key: str, *, default: Any = "") -> Any:
    if hasattr(snippet, key):
        return getattr(snippet, key)
    if isinstance(snippet, dict):
        return snippet.get(key, default)
    return default


def _transcript_segments_to_sectioned_text(segments: list[dict[str, Any]]) -> str:
    if not segments:
        return ""

    grouped: list[tuple[str, list[str]]] = []
    current_bucket = -1
    current_heading = ""
    current_lines: list[str] = []

    for segment in segments:
        text = normalize_whitespace(str(segment.get("text", "")))
        if not text:
            continue

        start = float(segment.get("start", 0.0) or 0.0)
        bucket = int(start // 300)
        heading = f"## {_format_seconds(bucket * 300)}-{_format_seconds((bucket + 1) * 300)}"

        if bucket != current_bucket:
            if current_lines:
                grouped.append((current_heading, current_lines))
            current_bucket = bucket
            current_heading = heading
            current_lines = [text]
        else:
            if current_lines and current_lines[-1] == text:
                continue
            current_lines.append(text)

    if current_lines:
        grouped.append((current_heading, current_lines))

    rendered_sections: list[str] = []
    for heading, lines in grouped:
        paragraph = _paragraphize_transcript_lines(lines)
        if paragraph:
            rendered_sections.append(f"{heading}\n\n{paragraph}")

    return "\n\n".join(rendered_sections).strip()


def _paragraphize_transcript_lines(lines: list[str]) -> str:
    merged_lines = _merge_transcript_lines(lines)
    combined = " ".join(merged_lines).strip()
    if not combined:
        return ""

    sentences = re.split(r"(?<=[.!?])\s+", combined)
    paragraphs: list[str] = []
    current: list[str] = []
    current_words = 0
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        words = len(sentence.split())
        if current and current_words + words > 110:
            paragraphs.append(" ".join(current).strip())
            current = [sentence]
            current_words = words
        else:
            current.append(sentence)
            current_words += words
    if current:
        paragraphs.append(" ".join(current).strip())
    return "\n\n".join(paragraphs)


def _normalize_transcript_line(text: str) -> str:
    clean = normalize_whitespace(text)
    clean = re.sub(r"\[(?:Music|Applause|Laughter)\]", "", clean, flags=re.I).strip()
    clean = re.sub(r"\s+([,.;!?])", r"\1", clean)
    return clean


def _append_transcript_segment(
    segments: list[dict[str, Any]],
    start: float,
    duration: float,
    text: str,
) -> None:
    clean = _normalize_transcript_line(text)
    if not clean:
        return
    if segments:
        previous = str(segments[-1]["text"])
        if clean == previous:
            return
        for prior in reversed(segments[-6:]):
            if str(prior["text"]) == clean and abs(float(prior.get("start", 0.0)) - start) <= 30:
                return
        overlap = _suffix_prefix_overlap(previous, clean)
        if overlap >= 4:
            clean = " ".join(clean.split()[overlap:]).strip()
            if not clean:
                return
    segments.append({"start": start, "duration": duration, "text": clean})


def _merge_transcript_lines(lines: list[str]) -> list[str]:
    merged: list[str] = []
    for raw_line in lines:
        line = _normalize_transcript_line(raw_line)
        if not line:
            continue
        if merged:
            previous = merged[-1]
            if line == previous:
                continue
            overlap = _suffix_prefix_overlap(previous, line)
            if overlap >= 4:
                line = " ".join(line.split()[overlap:])
                if not line:
                    continue
        merged.append(line)
    return merged


def _suffix_prefix_overlap(left: str, right: str) -> int:
    left_words = left.split()
    right_words = right.split()
    max_overlap = min(len(left_words), len(right_words), 12)
    for size in range(max_overlap, 0, -1):
        if left_words[-size:] == right_words[:size]:
            return size
    return 0


def _transcript_sections(transcript_text: str) -> list[str]:
    return re.findall(r"^##\s+.+$", transcript_text, flags=re.MULTILINE)


def _transcript_quality_label(
    *,
    transcript_available: bool,
    is_auto_caption: bool,
    quality: str,
) -> str:
    if not transcript_available:
        return "unavailable"
    if is_auto_caption:
        return f"auto_captions/{quality}"
    return f"manual_captions/{quality}"


def _format_seconds(total_seconds: int | float) -> str:
    total = int(max(total_seconds, 0))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _timestamp_to_seconds(value: str) -> float:
    match = _TIMESTAMP_RE.search(value.strip())
    if not match:
        return 0.0

    hours = match.group("hours")
    minutes = match.group("minutes")
    seconds = match.group("seconds")
    total = int(minutes) * 60 + int(seconds)
    if hours:
        total += int(hours[:-1]) * 3600
    return float(total)


def _build_youtube_archive_markdown(
    *,
    title: str,
    source_url: str,
    channel: str,
    duration: str,
    description: str,
    transcript_text: str,
    caption_type: str,
    extraction_method: str,
    extraction_quality: str,
) -> str:
    lines = [f"# {title}", "", f"> Source: {source_url}"]
    if channel:
        lines.append(f"> Channel: {channel}")
    if duration:
        lines.append(f"> Duration: {duration}")
    lines.append(
        f"> Transcript: {'available' if transcript_text else 'unavailable'}"
        + (f" ({caption_type})" if transcript_text and caption_type != "none" else "")
    )
    lines.append(f"> Extraction: {extraction_method} ({extraction_quality})")

    if description:
        lines.extend(["", "## Description", "", description.strip()])

    if transcript_text:
        lines.extend(["", "## Transcript", "", transcript_text.strip()])
    else:
        lines.extend(
            [
                "",
                "## Transcript",
                "",
                (
                    "_Transcript was unavailable during ingest. This raw note preserves "
                    "metadata only._"
                ),
            ]
        )

    return "\n".join(lines).strip()


async def _fetch_video_metadata(
    video_id: str, existing_title: str, *, timeout: int
) -> tuple[str, str, str, str]:
    """Fetch title, channel, description, duration via noembed and oembed."""
    title = "" if _looks_like_url(existing_title) else existing_title
    channel = ""
    description = ""
    duration = ""

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                f"https://noembed.com/embed?url=https://www.youtube.com/watch?v={video_id}"
            )
            if resp.status_code == 200:
                data = resp.json()
                if not title:
                    title = data.get("title", "")
                channel = data.get("author_name", "")
    except Exception:
        pass

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                "https://www.youtube.com/oembed",
                params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            )
            if resp.status_code == 200:
                data = resp.json()
                if not title:
                    title = data.get("title", "")
                if not channel:
                    channel = data.get("author_name", "")
    except Exception:
        pass

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            page_resp = await client.get(f"https://www.youtube.com/watch?v={video_id}")
            if page_resp.status_code == 200:
                text = page_resp.text
                desc_match = re.search(
                    r'"shortDescription"\s*:\s*"((?:[^"\\]|\\.)*)"', text
                )
                if desc_match:
                    raw = desc_match.group(1)
                    description = raw.encode().decode("unicode_escape", errors="replace")
                dur_match = re.search(r'"lengthSeconds"\s*:\s*"(\d+)"', text)
                if dur_match:
                    duration = _format_seconds(int(dur_match.group(1)))
    except Exception:
        pass

    return title, channel, description, duration


async def local_asr_hook(video_id: str) -> str | None:
    """Extension point for local ASR (e.g. Whisper). Not implemented — returns None."""
    return None
