"""LangGraph ingest workflow — turns a SourceItem into vault notes."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.backends.models import TaskName
from app.compiler.llm import run_structured, run_text
from app.compiler.prompts import (
    SOURCE_ANALYSIS_JSON_SCHEMA,
    SOURCE_ANALYSIS_PROMPT,
    SYSTEM_ROLE,
    YOUTUBE_ANALYSIS_RULES,
    YOUTUBE_CHUNK_DIGEST_SYSTEM,
    YOUTUBE_CHUNK_DIGEST_USER,
)
from app.connectors.fetchers import fetch_content
from app.models.db import ProcessedSource, VaultNoteMapping
from app.models.knowledge import Concept, Entity, Topic
from app.models.results import IngestResult, VaultUpdate
from app.models.source import SourceContent, SourceItem
from app.storage.repositories import SourceRepository, VaultNoteRepository
from app.storage.sqlite import Database
from app.utils.hashing import url_hash as compute_url_hash
from app.utils.slugify import slugify
from app.vault.index_updater import rebuild_indexes
from app.vault.log_updater import append_ingest_log
from app.vault.parser import scan_vault
from app.vault.writer import VaultWriter

logger = logging.getLogger(__name__)

_HEADING_RE = re.compile(r"^(#{1,6}\s+.+)$", re.MULTILINE)
_SECTION_LINE_RE = re.compile(r"^[A-Z][^:]{0,100}:$")
_QUOTE_RE = re.compile(r'"([^"\n]{8,180})"')
_YOUTUBE_SECTION_RE = re.compile(r"^##\s+(\d{2}:\d{2}-\d{2}:\d{2})\s*$", re.MULTILINE)


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text.strip())


def _canonical_name_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _paragraphs(text: str) -> list[str]:
    return [chunk.strip() for chunk in re.split(r"\n\s*\n", text) if chunk.strip()]


def _clip_paragraphs(text: str, *, max_paragraphs: int, max_chars: int) -> str:
    selected: list[str] = []
    total = 0
    for paragraph in _paragraphs(_collapse_whitespace(text)):
        if len(selected) >= max_paragraphs:
            break
        if total and total + len(paragraph) > max_chars:
            break
        selected.append(paragraph)
        total += len(paragraph)
    excerpt = "\n\n".join(selected).strip()
    return excerpt[:max_chars].rstrip()


def _bullet_list(items: list[str], default: str) -> str:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = item.strip().lstrip("-*•→ ").strip()
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(f"- {normalized}")
    return "\n".join(cleaned) or default


def _candidate_lines(text: str) -> list[str]:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            stripped = stripped.lstrip("#").strip()
        lines.append(stripped)
    return lines


def _extract_key_points(text: str, *, limit: int = 5) -> list[str]:
    points: list[str] = []
    for line in _candidate_lines(text):
        if line.startswith(("->", "=>", "→", "-", "*", "•")):
            points.append(line)
        elif 35 <= len(line) <= 180 and (":" in line or "." in line):
            points.append(line)
        if len(points) >= limit:
            break

    if points:
        return points[:limit]

    paragraphs = _paragraphs(text)
    fallback = []
    for paragraph in paragraphs[:limit]:
        sentence = paragraph.split(". ")[0].strip()
        if sentence:
            fallback.append(sentence.rstrip(".") + ".")
    return fallback[:limit]


def _extract_section_titles(text: str, *, limit: int = 6) -> list[str]:
    titles: list[str] = []
    seen: set[str] = set()

    for match in _HEADING_RE.findall(text):
        title = match.lstrip("#").strip()
        if title and title not in seen:
            seen.add(title)
            titles.append(title)
        if len(titles) >= limit:
            return titles

    for line in _candidate_lines(text):
        if _SECTION_LINE_RE.match(line):
            title = line.removesuffix(":").strip()
            if title and title not in seen:
                seen.add(title)
                titles.append(title)
        if len(titles) >= limit:
            break

    return titles[:limit]


def _fallback_outline(text: str) -> str:
    titles = _extract_section_titles(text)
    if titles:
        sections = []
        for title in titles:
            sections.append(f"## {title}\n- Captured in the raw archive and provisional note.")
        return "\n\n".join(sections)

    excerpt = _clip_paragraphs(text, max_paragraphs=4, max_chars=1800)
    return "## Captured Structure\n" + excerpt


def _fallback_quotes(text: str) -> str:
    quotes: list[str] = []
    for quote in _QUOTE_RE.findall(text):
        words = quote.split()
        if len(words) > 20:
            quote = " ".join(words[:20]).rstrip(",.;:") + " ..."
        quotes.append(f'"{quote}"')
        if len(quotes) >= 3:
            break
    return _bullet_list(quotes, "- None captured verbatim.")


def _youtube_sections(text: str) -> list[tuple[str, str]]:
    matches = list(_YOUTUBE_SECTION_RE.finditer(text))
    if not matches:
        return []

    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sections.append((match.group(1), body))
    return sections


def _section_excerpt(body: str, *, max_paragraphs: int, max_chars: int) -> str:
    excerpt = _clip_paragraphs(body, max_paragraphs=max_paragraphs, max_chars=max_chars)
    if excerpt:
        return excerpt
    return body.strip()[:max_chars].rstrip()


def _youtube_five_minute_read(text: str) -> str:
    sections = _youtube_sections(text)
    if not sections:
        return _clip_paragraphs(text, max_paragraphs=3, max_chars=1500)

    parts = []
    for label, body in sections[:3]:
        parts.append(f"**{label}**\n{_section_excerpt(body, max_paragraphs=2, max_chars=700)}")
    return "\n\n".join(parts)


def _youtube_detailed_fallback(text: str) -> str:
    sections = _youtube_sections(text)
    if not sections:
        return _clip_paragraphs(text, max_paragraphs=5, max_chars=2400)

    parts = [
        (
            "This provisional article version is built directly from the captured transcript. "
            "It is intended to be readable enough to review the video without immediately "
            "watching it, while the raw transcript remains preserved separately."
        )
    ]
    for label, body in sections[:5]:
        parts.append(f"### {label}\n{_section_excerpt(body, max_paragraphs=2, max_chars=900)}")
    return "\n\n".join(parts)


def _youtube_key_points(text: str) -> list[str]:
    points = []
    for label, body in _youtube_sections(text)[:5]:
        excerpt = _section_excerpt(body, max_paragraphs=1, max_chars=180)
        if excerpt:
            points.append(f"{label}: {excerpt}")
    return points


def _chunk_plain_text_for_ingest(text: str, max_chunk_chars: int) -> list[str]:
    """Split non-sectioned text into bounded chunks (paragraph-aware)."""
    if len(text) <= max_chunk_chars:
        return [text] if text.strip() else []

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chunk_chars, len(text))
        if end < len(text):
            split_at = text.rfind("\n\n", start, end)
            if split_at > start + max_chunk_chars // 4:
                end = split_at
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end if end > start else len(text)
    return chunks


def _youtube_transcript_chunks(text: str, max_chunk_chars: int) -> list[str]:
    """Split a YouTube capture into chunks at ## MM:SS-MM:SS boundaries when possible."""
    matches = list(_YOUTUBE_SECTION_RE.finditer(text))
    if not matches:
        return _chunk_plain_text_for_ingest(text, max_chunk_chars)

    sections: list[str] = []
    for index, match in enumerate(matches):
        sec_start = match.start()
        sec_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append(text[sec_start:sec_end].strip())

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for sec in sections:
        addition = len(sec) + 2
        if current and current_len + addition > max_chunk_chars:
            chunks.append("\n\n".join(current))
            current = [sec]
            current_len = len(sec)
        else:
            current.append(sec)
            current_len += addition
    if current:
        chunks.append("\n\n".join(current))
    return chunks


async def _prepare_ingest_evidence(content: SourceContent, text: str) -> tuple[str, str]:
    """Select or compile text for the main analysis prompt. Returns (evidence, optional note)."""
    from app.config import get_settings

    settings = get_settings()
    if content.source.source_type.value != "youtube":
        cap = settings.ingest_evidence_max_chars
        return text[:cap], ""

    cap = settings.ingest_youtube_evidence_max_chars or settings.ingest_evidence_max_chars
    chunk_size = max(4000, settings.ingest_youtube_chunk_chars)

    if len(text) <= cap:
        return text, ""

    title = content.source.title or content.source.url
    chunks = _youtube_transcript_chunks(text, chunk_size)
    digests: list[str] = []
    for index, chunk in enumerate(chunks):
        resp = await run_text(
            TaskName.INGEST,
            system_prompt=YOUTUBE_CHUNK_DIGEST_SYSTEM,
            user_prompt=YOUTUBE_CHUNK_DIGEST_USER.format(
                title=title,
                part=index + 1,
                total=len(chunks),
                chunk=chunk,
            ),
        )
        if resp.success and (resp.text or "").strip():
            digests.append(
                f"## Segment {index + 1} / {len(chunks)}\n\n{resp.text.strip()}"
            )
        else:
            err = resp.error or "empty response"
            logger.warning(
                "YouTube chunk digest failed (part %s/%s): %s",
                index + 1,
                len(chunks),
                err,
            )
            excerpt = chunk[:6000]
            digests.append(
                f"## Segment {index + 1} / {len(chunks)}\n\n"
                f"_Digest unavailable ({err}). Raw excerpt:_\n\n{excerpt}"
            )

    preamble = (
        "[The evidence below was assembled from chronological segment digests because the raw "
        f"transcript ({len(text)} characters) exceeded the single-pass analysis budget ({cap} "
        "characters). The full verbatim transcript is preserved in the vault raw capture.]\n\n"
    )
    compiled = preamble + "\n\n---\n\n".join(digests)
    note = (
        f"Analysis used {len(chunks)} transcript segment digests "
        f"(original transcript {len(text)} chars)."
    )
    if len(compiled) > cap:
        compiled = compiled[:cap].rsplit("\n", 1)[0] + "\n\n[…Truncated for analysis pass.]"
        note += " Compiled digest text was truncated to the analysis budget."
    return compiled, note


def _fallback_reading_note(content: SourceContent, text: str) -> str:
    source_type = content.source.source_type.value
    if source_type == "youtube":
        return _youtube_detailed_fallback(text)

    intro = _clip_paragraphs(text, max_paragraphs=4, max_chars=2200)
    if not intro:
        intro = (
            "The raw archive contains the captured text, but a readable excerpt could not be "
            "assembled."
        )
    guidance = {
        "youtube": (
            "Treat this as a provisional reading version of the video. The raw transcript "
            "is preserved separately, so this note is mainly here to keep the captured ideas "
            "readable while the full model-written analysis is unavailable."
        ),
        "article": (
            "Treat this as a provisional article note built directly from the captured body. "
            "The archived readable article remains the primary source of truth."
        ),
        "x_thread": (
            "Treat this as a provisional thread note. It preserves the main claims and examples "
            "from the captured thread text, but context or linked media may still be missing."
        ),
    }.get(
        source_type,
        "Treat this as a provisional reading note built directly from the captured text.",
    )

    return (
        f"{guidance}\n\n"
        "## What This Source Covers\n\n"
        f"{intro}"
    )


class IngestState(TypedDict, total=False):
    item: SourceItem
    content: SourceContent
    slug: str
    force_reingest: bool
    analysis: dict[str, Any]
    topics: list[Topic]
    entities: list[Entity]
    concepts: list[Concept]
    vault_updates: list[VaultUpdate]
    result: IngestResult
    deduplicated: bool
    duplicate_of: ProcessedSource
    error: str


def _source_specific_guidance(content: SourceContent) -> str:
    guidance: list[str] = [
        "Prefer concrete mechanisms, examples, and tensions over generic summary phrasing.",
        "Assume the note should remain useful months later as part of a growing wiki.",
        (
            "Write with the expectation that future sources will update this wiki "
            "rather than replace it."
        ),
    ]

    source_type = content.source.source_type.value
    if source_type == "youtube":
        guidance.extend(
            [
                (
                    "Apply the numbered YouTube rules in the main prompt: full-arc article, "
                    "chapters with timestamps in detailed_outline, synthesized prose "
                    "(not transcript echo)."
                ),
                "Help the reader decide whether they still need to watch the full video.",
                (
                    "If the transcript feels noisy, promote the speaker's real argument "
                    "and compress filler."
                ),
            ]
        )
    elif source_type == "article":
        guidance.extend(
            [
                "Preserve the article's argument, structure, and why it matters.",
                (
                    "Treat the raw readable article archive as the evidence layer and "
                    "this note as the compiled layer."
                ),
            ]
        )
    elif source_type == "x_thread":
        guidance.extend(
            [
                "Capture the sequence of claims and missing context if the thread is thin.",
                (
                    "Differentiate between what the thread directly states and what "
                    "remains implied or unsupported."
                ),
            ]
        )
    elif source_type == "pdf":
        guidance.extend(
            [
                "Preserve definitions, evidence, and structural cues from the document.",
                (
                    "Keep terminology crisp enough that the note can serve as a "
                    "durable reference page later."
                ),
            ]
        )

    if content.extraction_quality in {"metadata_only", "failed"}:
        guidance.append(
            "This extraction is incomplete. Be explicit about missing coverage "
            "and avoid overclaiming."
        )
    else:
        guidance.append(
            "Assume the reader wants to learn efficiently from this note before "
            "deciding whether to open the original."
        )

    return "\n".join(f"- {line}" for line in guidance)


def _existing_knowledge_lookup(vault_path: Path) -> dict[str, dict[str, str]]:
    lookup = {"topic": {}, "entity": {}, "concept": {}}
    for note in scan_vault(vault_path):
        if note.note_type not in lookup:
            continue
        title = note.title.strip()
        if not title:
            continue
        lookup[note.note_type].setdefault(slugify(title), title)
        lookup[note.note_type].setdefault(_canonical_name_key(title), title)
    return lookup


def _existing_knowledge_prompt(lookup: dict[str, dict[str, str]]) -> str:
    lines: list[str] = []
    for note_type, label in (
        ("topic", "Topics"),
        ("entity", "Entities"),
        ("concept", "Concepts"),
    ):
        names = sorted({title for title in lookup[note_type].values()})
        if names:
            lines.append(f"- {label}: {', '.join(names[:40])}")
        else:
            lines.append(f"- {label}: none yet")
    return "\n".join(lines)


def _resolve_existing_name(existing: dict[str, str], name: str) -> str:
    return existing.get(slugify(name)) or existing.get(_canonical_name_key(name)) or name


def _fallback_analysis(
    *,
    summary: str,
    five_minute_read: str,
    detailed_reading_note: str,
    key_ideas: str,
    detailed_outline: str,
    important_examples: str,
    actionable_takeaways: str,
    notable_quotes: str,
    best_for: str,
    consume_recommendation: str,
    why_it_matters: str,
    open_questions: str,
) -> dict[str, Any]:
    return {
        "summary": summary,
        "five_minute_read": five_minute_read,
        "detailed_reading_note": detailed_reading_note,
        "key_ideas": key_ideas,
        "detailed_outline": detailed_outline,
        "important_examples": important_examples,
        "actionable_takeaways": actionable_takeaways,
        "notable_quotes": notable_quotes,
        "best_for": best_for,
        "consume_recommendation": consume_recommendation,
        "why_it_matters": why_it_matters,
        "open_questions": open_questions,
        "topics": [],
        "entities": [],
        "concepts": [],
    }


def _normalize_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    baseline = _fallback_analysis(
        summary="Summary unavailable.",
        five_minute_read="Detailed briefing unavailable.",
        detailed_reading_note="Detailed reading note unavailable.",
        key_ideas="- No key ideas extracted yet.",
        detailed_outline="## Coverage\n- Outline unavailable.",
        important_examples="- No concrete examples captured.",
        actionable_takeaways="- No actionable takeaways extracted.",
        notable_quotes="- None captured verbatim.",
        best_for="- General manual review.",
        consume_recommendation="Consult the original source if it matters for a decision.",
        why_it_matters="This source is stored in the vault but still needs stronger analysis.",
        open_questions="- What is still missing from this capture?",
    )

    legacy_key_map = {
        "key_takeaways": "key_ideas",
        "important_claims": "important_examples",
        "why_matters": "why_it_matters",
    }
    for old_key, new_key in legacy_key_map.items():
        if analysis.get(old_key) and not analysis.get(new_key):
            analysis[new_key] = analysis[old_key]

    normalized = dict(baseline)
    for key in baseline:
        if key in {"topics", "entities", "concepts"}:
            continue
        value = analysis.get(key)
        if isinstance(value, str) and value.strip():
            normalized[key] = value.strip()

    normalized["topics"] = analysis.get("topics") or []
    normalized["entities"] = analysis.get("entities") or []
    normalized["concepts"] = analysis.get("concepts") or []
    return normalized


async def _fetch_content(state: IngestState) -> dict:
    item = state["item"]
    content = await fetch_content(item)
    slug = slugify(content.source.title or item.url)
    return {"content": content, "slug": slug}


async def _check_dedup(state: IngestState) -> dict:
    from app.config import get_settings

    content: SourceContent = state["content"]
    if state.get("force_reingest"):
        return {}
    settings = get_settings()
    db = Database(settings.db_path)
    db.connect()

    try:
        source_repo = SourceRepository(db)

        existing = source_repo.find_by_url_hash(
            content.url_hash or compute_url_hash(content.source.url)
        )
        if existing is None and content.content_hash:
            existing = source_repo.find_by_content_hash(content.content_hash)

        if existing and existing.status == "completed":
            result = IngestResult(
                source_url=content.source.url,
                source_title=content.source.title or existing.title,
                source_type=existing.source_type or content.source.source_type.value,
                source_note_path=existing.source_note_path,
                raw_capture_path=existing.raw_capture_path,
                deduplicated=True,
            )
            return {"deduplicated": True, "duplicate_of": existing, "result": result}

        return {}
    finally:
        db.close()


async def _analyse_content(state: IngestState) -> dict:
    from app.config import get_settings

    content: SourceContent = state["content"]
    text = content.cleaned_text or content.raw_text
    settings = get_settings()
    existing_lookup = _existing_knowledge_lookup(Path(settings.vault_path))

    if content.extraction_quality == "metadata_only":
        extraction_note = content.extraction_notes or "Only metadata was captured for this source."
        title = content.source.title or content.source.url
        metadata_excerpt = (content.cleaned_text or content.raw_text).strip()
        return {
            "analysis": _fallback_analysis(
                summary=(
                    f"Metadata-only capture for '{title}'. The source was saved, but the full body "
                    "text was not extracted."
                ),
                five_minute_read=(
                    f"Only limited metadata was available for '{title}'. "
                    f"Captured excerpt: {metadata_excerpt[:800] or 'No excerpt available.'}"
                ),
                detailed_reading_note=(
                    "This note is intentionally limited. The source appears potentially useful, "
                    "but ingest only recovered metadata or a short excerpt."
                ),
                key_ideas=(
                    "- The source is preserved in the vault for follow-up\n"
                    "- Full body extraction did not succeed during this ingest\n"
                    f"- Extraction note: {extraction_note}"
                ),
                detailed_outline=(
                    "## Capture Status\n- Metadata-only ingest\n- Full structure unavailable\n\n"
                    f"## Captured Excerpt\n- {metadata_excerpt[:1500] or 'No excerpt available.'}"
                ),
                important_examples="- No concrete examples were captured from the source body.",
                actionable_takeaways=(
                    "- Revisit the original source if this item becomes important\n"
                    "- Consider re-ingesting later with a stronger extraction path"
                ),
                notable_quotes="- None captured verbatim.",
                best_for="- Deciding whether this source deserves manual review.",
                consume_recommendation=(
                    "The original source is still worth opening if this bookmark seems important, "
                    "because the vault did not capture the full content."
                ),
                why_it_matters=(
                    "This source may still matter as a pointer inside the vault, but it should not "
                    "be treated as fully compiled knowledge yet."
                ),
                open_questions=(
                    "- Can the full text or transcript be captured later?\n"
                    "- Is this source important enough to review manually?"
                ),
            )
        }

    if not text or content.extraction_quality == "failed":
        return {
            "analysis": _fallback_analysis(
                summary="Content could not be extracted from this source.",
                five_minute_read=(
                    "The ingest failed before usable content was captured, so this "
                    "note records only the failed attempt."
                ),
                detailed_reading_note=(
                    "No detailed reading note is possible yet because the source "
                    "body or transcript was not recovered."
                ),
                key_ideas="- Extraction failed or returned empty content.",
                detailed_outline="## Capture Status\n- Extraction failed",
                important_examples="- No examples were captured.",
                actionable_takeaways="- Retry the source later or inspect it manually.",
                notable_quotes="- None captured verbatim.",
                best_for="- Tracking ingest failures that need follow-up.",
                consume_recommendation=(
                    "Open the original source directly if it matters; the vault does not have a "
                    "reliable capture yet."
                ),
                why_it_matters=(
                    "The bookmark remains part of the vault history even though "
                    "automated compilation failed."
                ),
                open_questions=(
                    "- Why did extraction fail?\n"
                    "- Should this source be retried with another method?"
                ),
            ),
        }

    evidence_text, evidence_note = await _prepare_ingest_evidence(content, text)
    extraction_notes_prompt = content.extraction_notes or "none"
    if evidence_note:
        extraction_notes_prompt = (
            f"{extraction_notes_prompt}; {evidence_note}"
            if extraction_notes_prompt != "none"
            else evidence_note
        )

    is_youtube = content.source.source_type.value == "youtube"
    prompt = SOURCE_ANALYSIS_PROMPT.format(
        title=content.source.title or content.source.url,
        source_type=content.source.source_type.value,
        url=content.source.url,
        canonical_url=content.canonical_url or "N/A",
        author=content.author or "N/A",
        published_date=content.published_date or "N/A",
        tags=", ".join(content.source.tags) or "none",
        extraction_quality=content.extraction_quality,
        extraction_method=content.extraction_method or "unknown",
        extraction_notes=extraction_notes_prompt,
        source_specific_guidance=_source_specific_guidance(content),
        existing_knowledge=_existing_knowledge_prompt(existing_lookup),
        content=evidence_text,
        youtube_rules=YOUTUBE_ANALYSIS_RULES if is_youtube else "",
    )

    try:
        resp = await run_structured(
            task=TaskName.INGEST,
            system_prompt=SYSTEM_ROLE,
            user_prompt=prompt,
            json_schema_hint=SOURCE_ANALYSIS_JSON_SCHEMA,
        )
        if resp.success:
            analysis = _normalize_analysis(json.loads(resp.text))
            logger.info(
                "Ingest analysis via %s (model=%s, fallback=%s)",
                resp.backend_used,
                resp.model_used,
                resp.was_fallback,
            )
        else:
            raise RuntimeError(resp.error)
    except Exception as exc:
        logger.warning("LLM analysis failed: %s", exc)
        source_type = content.source.source_type.value
        fb_cap = (
            settings.ingest_youtube_evidence_max_chars or settings.ingest_evidence_max_chars
            if source_type == "youtube"
            else settings.ingest_evidence_max_chars
        )
        fallback_text = text[:fb_cap]
        excerpt = (
            _youtube_five_minute_read(fallback_text)
            if source_type == "youtube"
            else _clip_paragraphs(fallback_text, max_paragraphs=4, max_chars=1500)
        )
        key_points = (
            _youtube_key_points(fallback_text)
            if source_type == "youtube"
            else _extract_key_points(fallback_text)
        )
        analysis = _fallback_analysis(
            summary=(
                f"Structured auto-analysis failed ({exc}), but the source text was captured "
                "and preserved for review."
            ),
            five_minute_read=(
                excerpt
                or "The source text was captured, but a short briefing could not be assembled."
            ),
            detailed_reading_note=_fallback_reading_note(content, fallback_text),
            key_ideas=_bullet_list(
                key_points[:5],
                "- The source text was captured, but structured analysis failed.",
            ),
            detailed_outline=_fallback_outline(fallback_text),
            important_examples=_bullet_list(
                key_points[1:6] if len(key_points) > 1 else key_points,
                "- Review the captured text directly for concrete examples.",
            ),
            actionable_takeaways=(
                "- Use the raw archive when exact wording or missing context matters.\n"
                "- Re-run ingest later if you want a fully linked model-written analysis.\n"
                "- Promote any durable insights from this note into topic or synthesis pages."
            ),
            notable_quotes=_fallback_quotes(fallback_text),
            best_for=(
                "- Fast review when the raw capture succeeded but the reasoning backend did not.\n"
                "- Manual follow-up on sources that look promising enough to revisit."
            ),
            consume_recommendation=(
                "The raw archive is usually enough for a first pass, but the original source is "
                "still worth opening when presentation, media, or surrounding context matter."
            ),
            why_it_matters=(
                "The vault still retains the captured evidence and a readable provisional note, "
                "so this source remains usable instead of becoming a dead-end ingest."
            ),
            open_questions=(
                "- Does this source deserve a retry for richer topic/entity/concept linking?\n"
                "- What context might still be missing from the captured text alone?"
            ),
        )

    return {"analysis": analysis}


async def _extract_knowledge(state: IngestState) -> dict:
    from app.config import get_settings

    analysis = state["analysis"]
    slug = state["slug"]
    topic_summary = analysis.get("summary", "").strip()
    settings = get_settings()
    existing_lookup = _existing_knowledge_lookup(Path(settings.vault_path))

    entity_names = [
        (
            _resolve_existing_name(existing_lookup["entity"], entity["name"])
            if isinstance(entity, dict)
            else _resolve_existing_name(existing_lookup["entity"], str(entity))
        )
        for entity in analysis.get("entities", [])
    ]
    concept_names = [
        (
            _resolve_existing_name(existing_lookup["concept"], concept["name"])
            if isinstance(concept, dict)
            else _resolve_existing_name(existing_lookup["concept"], str(concept))
        )
        for concept in analysis.get("concepts", [])
    ]

    topics = []
    for topic_name in analysis.get("topics", []):
        resolved_topic_name = _resolve_existing_name(existing_lookup["topic"], topic_name)
        topics.append(
            Topic(
                name=resolved_topic_name,
                slug=slugify(resolved_topic_name),
                summary=topic_summary,
                source_ids=[slug],
                related_entities=entity_names,
                related_concepts=concept_names,
            )
        )

    entities = []
    for entity_data in analysis.get("entities", []):
        if isinstance(entity_data, str):
            entity_data = {"name": entity_data, "type": "unknown", "description": ""}
        resolved_entity_name = _resolve_existing_name(
            existing_lookup["entity"], entity_data["name"]
        )
        entities.append(
            Entity(
                name=resolved_entity_name,
                slug=slugify(resolved_entity_name),
                entity_type=entity_data.get("type", "unknown"),
                description=entity_data.get("description", ""),
                source_ids=[slug],
                related_concepts=concept_names,
            )
        )

    concepts = []
    for concept_data in analysis.get("concepts", []):
        if isinstance(concept_data, str):
            concept_data = {"name": concept_data, "definition": ""}
        concept_name = _resolve_existing_name(existing_lookup["concept"], concept_data["name"])
        concepts.append(
            Concept(
                name=concept_name,
                slug=slugify(concept_name),
                definition=concept_data.get("definition", ""),
                source_ids=[slug],
                related_concepts=[name for name in concept_names if name and name != concept_name],
            )
        )

    return {"topics": topics, "entities": entities, "concepts": concepts}


async def _write_vault(state: IngestState) -> dict:
    from pathlib import Path

    from app.config import get_settings

    settings = get_settings()
    vault_path = Path(settings.vault_path)
    writer = VaultWriter(vault_path)
    writer.ensure_structure()

    content: SourceContent = state["content"]
    slug = state["slug"]
    analysis = state["analysis"]
    topics: list[Topic] = state.get("topics", [])
    entities: list[Entity] = state.get("entities", [])
    concepts: list[Concept] = state.get("concepts", [])

    updates: list[VaultUpdate] = []

    raw_update = writer.write_raw_capture(content, slug)
    updates.append(raw_update)

    source_update = writer.write_source_note(
        content=content,
        slug=slug,
        raw_capture_path=raw_update.path,
        summary=analysis.get("summary", ""),
        five_minute_read=analysis.get("five_minute_read", ""),
        detailed_reading_note=analysis.get("detailed_reading_note", ""),
        key_ideas=analysis.get("key_ideas", ""),
        detailed_outline=analysis.get("detailed_outline", ""),
        important_examples=analysis.get("important_examples", ""),
        actionable_takeaways=analysis.get("actionable_takeaways", ""),
        notable_quotes=analysis.get("notable_quotes", ""),
        best_for=analysis.get("best_for", ""),
        consume_recommendation=analysis.get("consume_recommendation", ""),
        why_it_matters=analysis.get("why_it_matters", ""),
        open_questions=analysis.get("open_questions", ""),
        topics=[topic.name for topic in topics],
        entities=[entity.name for entity in entities],
        concepts=[concept.name for concept in concepts],
    )
    updates.append(source_update)

    source_title = content.source.title or content.source.url

    for topic in topics:
        updates.append(writer.write_topic(topic, [source_title]))

    for entity in entities:
        updates.append(writer.write_entity(entity, [source_title]))

    for concept in concepts:
        updates.append(writer.write_concept(concept, [source_title]))

    rebuild_indexes(vault_path)

    return {"vault_updates": updates}


async def _persist_duplicate(state: IngestState) -> dict:
    from pathlib import Path

    from app.config import get_settings

    settings = get_settings()
    vault_path = Path(settings.vault_path)
    db = Database(settings.db_path)
    db.connect()

    try:
        content: SourceContent = state["content"]
        existing = state["duplicate_of"]
        result = state["result"]

        SourceRepository(db).upsert(
            ProcessedSource(
                url=content.source.url,
                url_hash=content.url_hash or compute_url_hash(content.source.url),
                content_hash=content.content_hash or existing.content_hash,
                source_type=existing.source_type or content.source.source_type.value,
                title=content.source.title or existing.title,
                source_note_path=existing.source_note_path,
                raw_capture_path=existing.raw_capture_path,
                provider=content.source.inbox_provider,
                external_id=content.source.external_id,
                provider_metadata=content.source.provider_metadata,
                status="completed",
            )
        )

        append_ingest_log(vault_path, result)
        return {}
    finally:
        db.close()


async def _persist_state(state: IngestState) -> dict:
    from pathlib import Path

    from app.config import get_settings

    settings = get_settings()
    vault_path = Path(settings.vault_path)
    db = Database(settings.db_path)
    db.connect()

    content: SourceContent = state["content"]
    slug = state["slug"]
    updates: list[VaultUpdate] = state.get("vault_updates", [])
    topics: list[Topic] = state.get("topics", [])
    entities: list[Entity] = state.get("entities", [])
    concepts: list[Concept] = state.get("concepts", [])

    source_repo = SourceRepository(db)
    note_repo = VaultNoteRepository(db)

    source_note_path = ""
    raw_path = ""
    for update in updates:
        if update.note_type == "source":
            source_note_path = update.path
        elif update.note_type == "raw_capture":
            raw_path = update.path

    source_repo.upsert(
        ProcessedSource(
            url=content.source.url,
            url_hash=content.url_hash or compute_url_hash(content.source.url),
            content_hash=content.content_hash or "",
            source_type=content.source.source_type.value,
            title=content.source.title or content.source.url,
            source_note_path=source_note_path,
            raw_capture_path=raw_path,
            provider=content.source.inbox_provider,
            external_id=content.source.external_id,
            provider_metadata=content.source.provider_metadata,
            status="completed",
        )
    )

    for update in updates:
        if update.note_type in ("source", "topic", "entity", "concept", "synthesis"):
            note_repo.upsert(
                VaultNoteMapping(
                    note_path=update.path,
                    note_type=update.note_type,
                    slug=slug if update.note_type == "source" else "",
                    title=(content.source.title or content.source.url)
                    if update.note_type == "source"
                    else "",
                    source_url=content.source.url if update.note_type == "source" else "",
                )
            )

    result = IngestResult(
        source_url=content.source.url,
        source_title=content.source.title or content.source.url,
        source_type=content.source.source_type.value,
        source_note_path=source_note_path,
        raw_capture_path=raw_path,
        extraction_quality=content.extraction_quality,
        extraction_method=content.extraction_method,
        bookmark_tags=content.source.tags,
        topics_updated=[topic.name for topic in topics],
        entities_updated=[entity.name for entity in entities],
        concepts_updated=[concept.name for concept in concepts],
        vault_updates=updates,
        deduplicated=state.get("deduplicated", False),
    )

    append_ingest_log(vault_path, result)

    db.close()
    return {"result": result}


def _route_after_dedup(state: IngestState) -> str:
    return "persist_duplicate" if state.get("deduplicated") else "analyse"


def build_ingest_graph() -> StateGraph:
    graph = StateGraph(IngestState)

    graph.add_node("fetch", _fetch_content)
    graph.add_node("dedup", _check_dedup)
    graph.add_node("persist_duplicate", _persist_duplicate)
    graph.add_node("analyse", _analyse_content)
    graph.add_node("extract_knowledge", _extract_knowledge)
    graph.add_node("write_vault", _write_vault)
    graph.add_node("persist", _persist_state)

    graph.add_edge(START, "fetch")
    graph.add_edge("fetch", "dedup")
    graph.add_conditional_edges(
        "dedup",
        _route_after_dedup,
        {
            "persist_duplicate": "persist_duplicate",
            "analyse": "analyse",
        },
    )
    graph.add_edge("persist_duplicate", END)
    graph.add_edge("analyse", "extract_knowledge")
    graph.add_edge("extract_knowledge", "write_vault")
    graph.add_edge("write_vault", "persist")
    graph.add_edge("persist", END)

    return graph


_compiled_graph = None


def get_ingest_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_ingest_graph().compile()
    return _compiled_graph
