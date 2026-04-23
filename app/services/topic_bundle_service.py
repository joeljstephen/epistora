"""Topic bundle generation service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.backends.models import TaskName
from app.compiler.llm import run_text
from app.compiler.prompts import compose_topic_bundle_prompt
from app.config import get_settings
from app.events import EventType, publish
from app.models.results import TopicBundleResult
from app.retrieval import RetrievalContext, build_retrieval_context
from app.utils.dates import utcnow
from app.utils.markdown import build_frontmatter_doc, parse_frontmatter
from app.utils.slugify import slugify
from app.vault.paths import topic_bundle_output_path


@dataclass(slots=True)
class BundleSource:
    note_path: str
    title: str
    source_type: str
    brief_status: str
    quick_summary: str
    best_next_action: str
    why_it_matters: str
    theme_tags: list[str]
    retrieval_score: float
    retrieval_reasons: list[str]
    snippet: str
    saved_at: datetime | None

    @property
    def is_ready(self) -> bool:
        return self.brief_status == "ready"

    @property
    def is_usable(self) -> bool:
        return self.brief_status in {"ready", "partial"}


async def generate_topic_bundle(
    topic: str,
    *,
    days: int | None = None,
    source_types: list[str] | None = None,
) -> TopicBundleResult:
    settings = get_settings()
    vault_path = Path(settings.vault_path)
    retrieval = _resolve_context(vault_path=vault_path, topic=topic)
    included_sources = _select_sources(
        vault_path=vault_path,
        retrieval=retrieval,
        days=days,
        source_types=source_types or [],
    )
    bundle_status = _bundle_status(included_sources)
    report = await _generate_report(
        vault_path=vault_path,
        topic=topic,
        retrieval=retrieval,
        included_sources=included_sources,
        bundle_status=bundle_status,
        days=days,
        source_types=source_types or [],
    )
    saved_to = _save_bundle(
        vault_path=vault_path,
        topic=topic,
        report=report,
        retrieval=retrieval,
        included_sources=included_sources,
        bundle_status=bundle_status,
        days=days,
        source_types=source_types or [],
    )
    ready_count = sum(1 for source in included_sources if source.is_ready)
    return TopicBundleResult(
        topic=topic,
        report=report,
        bundle_status=bundle_status,
        source_references=[source.note_path for source in included_sources],
        topics_consulted=retrieval.topics_consulted,
        source_count=len(included_sources),
        ready_source_count=ready_count,
        saved_to=saved_to,
        confidence=_confidence_label(bundle_status=bundle_status, ready_count=ready_count),
    )


def _resolve_context(*, vault_path: Path, topic: str) -> RetrievalContext:
    return build_retrieval_context(vault_path, topic, limit=12)


def _select_sources(
    *,
    vault_path: Path,
    retrieval: RetrievalContext,
    days: int | None,
    source_types: list[str],
) -> list[BundleSource]:
    normalized_types = {item.strip().lower() for item in source_types if item.strip()}
    selected: list[BundleSource] = []
    seen: set[str] = set()

    for artifact in retrieval.artifacts:
        note = artifact.note
        if note.note_type != "source":
            continue
        if note.note_path in seen:
            continue
        if normalized_types and note.source_type.lower() not in normalized_types:
            continue

        source = _bundle_source_from_note(
            vault_path=vault_path,
            note_path=note.note_path,
            title=note.title,
            source_type=note.source_type,
            retrieval_score=artifact.score,
            retrieval_reasons=artifact.reasons,
            snippet=artifact.snippet,
        )
        if not source.is_usable:
            continue
        if days is not None and not _within_days(source.saved_at, days):
            continue

        seen.add(note.note_path)
        selected.append(source)

    selected.sort(
        key=lambda source: (
            0 if source.is_ready else 1,
            -source.retrieval_score,
            source.title.lower(),
        )
    )
    return selected[:8]


def _bundle_source_from_note(
    *,
    vault_path: Path,
    note_path: str,
    title: str,
    source_type: str,
    retrieval_score: float,
    retrieval_reasons: list[str],
    snippet: str,
) -> BundleSource:
    meta, _ = parse_frontmatter((vault_path / note_path).read_text(encoding="utf-8"))
    saved_at_raw = str(meta.get("saved_at", "") or "").strip()
    return BundleSource(
        note_path=note_path,
        title=title,
        source_type=source_type,
        brief_status=str(meta.get("brief_status", "partial") or "partial").strip().lower(),
        quick_summary=str(meta.get("quick_summary", "") or "").strip(),
        best_next_action=str(meta.get("best_next_action", "") or "").strip()
        or str(meta.get("consume_recommendation", "") or "").strip(),
        why_it_matters=str(meta.get("why_it_matters", "") or "").strip(),
        theme_tags=[str(item) for item in meta.get("theme_tags", []) or []],
        retrieval_score=retrieval_score,
        retrieval_reasons=list(retrieval_reasons),
        snippet=snippet.strip(),
        saved_at=_parse_dt(saved_at_raw),
    )


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _within_days(saved_at: datetime | None, days: int) -> bool:
    if saved_at is None:
        return True
    cutoff = utcnow() - timedelta(days=days)
    return saved_at >= cutoff


def _bundle_status(sources: list[BundleSource]) -> str:
    ready_count = sum(1 for source in sources if source.is_ready)
    if len(sources) >= 3 and ready_count >= 2:
        return "normal"
    return "limited"


async def _generate_report(
    *,
    vault_path: Path,
    topic: str,
    retrieval: RetrievalContext,
    included_sources: list[BundleSource],
    bundle_status: str,
    days: int | None,
    source_types: list[str],
) -> str:
    if not included_sources:
        return _fallback_empty_bundle(topic=topic, retrieval=retrieval)

    filters = _filter_label(days=days, source_types=source_types)
    source_context = _source_context(included_sources)
    composition = compose_topic_bundle_prompt(
        workspace_path=vault_path,
        format_kwargs={
            "topic": topic,
            "bundle_status": bundle_status,
            "source_count": len(included_sources),
            "ready_source_count": sum(1 for source in included_sources if source.is_ready),
            "filters": filters,
            "source_context": source_context,
        },
    )

    try:
        response = await run_text(
            task=TaskName.TOPIC_BUNDLE,
            system_prompt=composition.system_prompt,
            user_prompt=composition.user_prompt,
        )
        if response.success and response.text.strip():
            return response.text.strip()
        raise RuntimeError(response.error or "empty response")
    except Exception:
        return _fallback_bundle(
            topic=topic,
            bundle_status=bundle_status,
            included_sources=included_sources,
        )


def _filter_label(*, days: int | None, source_types: list[str]) -> str:
    parts: list[str] = []
    if days is not None:
        parts.append(f"last {days} days")
    if source_types:
        parts.append(f"source types: {', '.join(source_types)}")
    return ", ".join(parts) if parts else "none"


def _source_context(sources: list[BundleSource]) -> str:
    blocks: list[str] = []
    for source in sources:
        blocks.append(
            "\n".join(
                [
                    f"### {source.title}",
                    f"- Path: {source.note_path}",
                    f"- Source type: {source.source_type}",
                    f"- Brief status: {source.brief_status}",
                    f"- Theme tags: {', '.join(source.theme_tags) or 'none'}",
                    f"- Retrieval reasons: {', '.join(source.retrieval_reasons) or 'structured retrieval'}",
                    f"- Quick summary: {source.quick_summary or 'Not available.'}",
                    f"- Best next action: {source.best_next_action or 'Not available.'}",
                    f"- Why it matters: {source.why_it_matters or 'Not available.'}",
                    f"- Snippet: {source.snippet or 'Not available.'}",
                ]
            )
        )
    return "\n\n".join(blocks)


def _fallback_empty_bundle(*, topic: str, retrieval: RetrievalContext) -> str:
    references = "\n".join(f"- {ref}" for ref in retrieval.source_references[:6]) or "- None"
    return (
        "## Topic Overview\n"
        f"This is a limited bundle for '{topic}' because the current vault retrieval set did not "
        "produce enough usable source notes.\n\n"
        "## Why This Matters\n"
        "The corpus may still contain related material, but not enough compiled source notes "
        "to support a normal topic packet.\n\n"
        "## Best Sources To Start With\n"
        "- No usable source briefs were selected.\n\n"
        "## What Each Source Contributed\n"
        "- No source-level contribution analysis is possible yet.\n\n"
        "## Agreements and Disagreements\n"
        "- No cross-source synthesis is possible from the current source set.\n\n"
        "## Key Concepts / Terms\n"
        "- None extracted for this limited bundle.\n\n"
        "## Recommended Order\n"
        "- Ingest or compile more relevant sources first.\n\n"
        "## If I Only Have 10 Minutes\n"
        "- Broaden the search terms or ingest more relevant sources.\n\n"
        "## Gaps / Missing Coverage\n"
        "- The source set is too sparse for a normal bundle.\n\n"
        "## Included Sources\n"
        f"{references}"
    )


def _fallback_bundle(
    *,
    topic: str,
    bundle_status: str,
    included_sources: list[BundleSource],
) -> str:
    top_sources = included_sources[:3]
    contribution_lines = []
    included_lines = []
    key_terms: list[str] = []
    for source in included_sources:
        if source.theme_tags:
            for tag in source.theme_tags:
                if tag not in key_terms:
                    key_terms.append(tag)
        included_lines.append(
            f"- {source.title} (`{source.source_type}`, {source.brief_status}) — `{source.note_path}`"
        )
        contribution_lines.append(
            f"- **{source.title}**: {source.quick_summary or source.snippet or 'Adds supporting context.'}"
        )

    best_start = "\n".join(
        f"- {source.title}: {source.best_next_action or source.quick_summary or 'Start here.'}"
        for source in top_sources
    ) or "- No strong starting source identified."
    concepts = "\n".join(f"- {term}" for term in key_terms[:8]) or "- No stable terms extracted."
    recommended_order = "\n".join(
        f"{index}. {source.title}"
        for index, source in enumerate(included_sources, start=1)
    ) or "1. Gather more sources"
    overview = (
        f"This is a {bundle_status} topic bundle for '{topic}' built from "
        f"{len(included_sources)} compiled source note(s)."
    )
    if bundle_status == "limited":
        overview += " Coverage is sparse or partially compiled, so conclusions remain provisional."

    return (
        "## Topic Overview\n"
        f"{overview}\n\n"
        "## Why This Matters\n"
        "This packet assembles the strongest currently retrieved source notes into one grounded "
        "starting point.\n\n"
        "## Best Sources To Start With\n"
        f"{best_start}\n\n"
        "## What Each Source Contributed\n"
        f"{chr(10).join(contribution_lines) or '- No source contribution notes available.'}\n\n"
        "## Agreements and Disagreements\n"
        "- The fallback bundle does not attempt strong disagreement synthesis.\n"
        "- Review the included sources directly when tradeoffs or conflicts matter.\n\n"
        "## Key Concepts / Terms\n"
        f"{concepts}\n\n"
        "## Recommended Order\n"
        f"{recommended_order}\n\n"
        "## If I Only Have 10 Minutes\n"
        f"{best_start}\n\n"
        "## Gaps / Missing Coverage\n"
        "- A stronger bundle would benefit from more ready briefs or a tighter topic query.\n\n"
        "## Included Sources\n"
        f"{chr(10).join(included_lines) or '- None'}"
    )


def _save_bundle(
    *,
    vault_path: Path,
    topic: str,
    report: str,
    retrieval: RetrievalContext,
    included_sources: list[BundleSource],
    bundle_status: str,
    days: int | None,
    source_types: list[str],
) -> str:
    timestamp = utcnow().strftime("%Y-%m-%d-%H%M%S")
    output_path = topic_bundle_output_path(vault_path, slugify(topic), timestamp)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    meta = {
        "title": f"Topic Bundle: {topic}",
        "type": "topic_bundle",
        "generated_at": utcnow().isoformat(timespec="seconds"),
        "topic_query": topic,
        "bundle_status": bundle_status,
        "source_count": len(included_sources),
        "ready_source_count": sum(1 for source in included_sources if source.is_ready),
        "days_filter": days,
        "source_types_filter": list(source_types),
        "included_source_paths": [source.note_path for source in included_sources],
        "topics_consulted": list(retrieval.topics_consulted),
    }
    content = build_frontmatter_doc(meta, report.strip())
    output_path.write_text(content, encoding="utf-8")

    rel_path = str(output_path.relative_to(vault_path))
    publish(
        EventType.TOPIC_BUNDLE_SAVED,
        topic=topic,
        saved_to=rel_path,
        source_references=[source.note_path for source in included_sources],
    )
    return rel_path


def _confidence_label(*, bundle_status: str, ready_count: int) -> str:
    if bundle_status == "normal" and ready_count >= 3:
        return "high"
    if ready_count >= 1:
        return "medium"
    return "low"
