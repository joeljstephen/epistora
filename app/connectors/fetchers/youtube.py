from __future__ import annotations

import re

import httpx

from app.models.source import SourceContent, SourceItem
from app.utils.hashing import content_hash, url_hash


def _extract_video_id(url: str) -> str | None:
    patterns = [
        r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([a-zA-Z0-9_-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


async def fetch_youtube(item: SourceItem) -> SourceContent:
    """Fetch YouTube video transcript and metadata."""
    video_id = _extract_video_id(item.url)
    if not video_id:
        return SourceContent(
            source=item,
            extraction_quality="failed",
            extraction_notes="Could not extract video ID from URL.",
            url_hash=url_hash(item.url),
        )

    transcript_text = ""
    extraction_notes = ""
    quality = "good"

    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(video_id)
        transcript_text = " ".join(snippet.text for snippet in transcript)
    except Exception as e:
        extraction_notes = (
            f"Transcript unavailable ({e}). "
            "Falling back to metadata-only ingest. "
            "This video may have disabled captions or be age-restricted."
        )
        quality = "metadata_only"

    title = item.title
    if not title:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"https://noembed.com/embed?url=https://www.youtube.com/watch?v={video_id}"
                )
                if resp.status_code == 200:
                    title = resp.json().get("title", "")
        except Exception:
            pass
        title = title or f"YouTube Video {video_id}"
    item.title = title

    raw_text = f"Video ID: {video_id}\nTitle: {title}\n\n{transcript_text}"

    return SourceContent(
        source=item,
        raw_text=raw_text,
        cleaned_text=transcript_text,
        word_count=len(transcript_text.split()) if transcript_text else 0,
        extraction_quality=quality,
        extraction_notes=extraction_notes,
        content_hash=content_hash(transcript_text) if transcript_text else "",
        url_hash=url_hash(item.url),
    )
