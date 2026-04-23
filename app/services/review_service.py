"""Deterministic daily and weekly review digest generation."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from app.config import get_settings
from app.events import EventType, publish
from app.models.lifecycle import StalenessStatus
from app.models.results import ReviewDigestResult
from app.storage.repositories import ReviewSurfaceHistoryRepository
from app.storage.sqlite import Database
from app.utils.dates import friendly_date, utcnow
from app.utils.markdown import build_frontmatter_doc, path_wikilink
from app.vault.parser import VaultNote, scan_vault
from app.vault.paths import daily_digest_output_path, weekly_digest_output_path

_USABLE_BRIEF_STATUSES = {"ready", "partial"}


@dataclass(slots=True)
class ReviewSource:
    note_path: str
    title: str
    source_type: str
    brief_status: str
    reading_state: str
    theme_tags: list[str]
    quick_summary: str
    best_next_action: str
    why_it_matters: str
    saved_at: datetime
    review_excluded: bool
    lifecycle_confidence: float | None
    lifecycle_last_confirmed_at: datetime | None
    lifecycle_staleness_status: str
    reinforcement_count: int

    @property
    def is_ready(self) -> bool:
        return self.brief_status == "ready"

    @property
    def is_usable(self) -> bool:
        return self.brief_status in _USABLE_BRIEF_STATUSES

    @property
    def preferred_theme(self) -> str:
        return self.theme_tags[0] if self.theme_tags else ""


@dataclass(slots=True)
class PreferenceProfile:
    theme_affinity: Counter[str]

    @property
    def active_themes(self) -> list[str]:
        return [theme for theme, _ in self.theme_affinity.most_common(3)]


async def generate_daily_digest(
    *,
    reference_date: date | None = None,
) -> ReviewDigestResult:
    target_date = reference_date or utcnow().date()
    settings = get_settings()
    vault_path = Path(settings.vault_path)
    db = Database(settings.db_path)
    db.connect()

    try:
        history_repo = ReviewSurfaceHistoryRepository(db)
        period_key = target_date.isoformat()
        output_path = daily_digest_output_path(vault_path, period_key)
        sources = _load_sources(vault_path)
        eligible_sources = [
            source for source in sources if source.is_usable and not source.review_excluded
        ]
        theme_counts = _theme_counts(eligible_sources)
        period_start = _day_start(target_date)
        recent_cutoff = period_start - timedelta(days=3)

        history_rows = history_repo.list_surfaces_since(
            since=period_start - timedelta(days=21),
            exclude_period_key=period_key,
        )
        last_surface = _last_surface_map(history_rows)
        preference_profile = _build_preference_profile(
            sources=eligible_sources,
            history_rows=history_rows,
        )

        recent_sources = [
            source for source in eligible_sources if source.saved_at >= recent_cutoff
        ]
        recent_selected = sorted(
            recent_sources,
            key=lambda source: _daily_recent_rank(
                source,
                theme_counts=theme_counts,
                preference_profile=preference_profile,
            ),
        )[:3]

        resurfaced_source = _choose_resurfaced_source(
            sources=eligible_sources,
            theme_counts=theme_counts,
            last_surface=last_surface,
            period_start=period_start,
            already_selected={source.note_path for source in recent_selected},
            preference_profile=preference_profile,
        )

        published, skip_reason = _daily_publish_decision(
            recent_selected=recent_selected,
            resurfaced_source=resurfaced_source,
        )
        if not published:
            history_repo.clear_period(review_type="daily", period_key=period_key)
            if output_path.exists():
                output_path.unlink()
            return ReviewDigestResult(
                review_type="daily",
                period_key=period_key,
                digest_status="skipped",
                reason=skip_reason,
            )

        included_sources = list(recent_selected)
        surfaced_entries: list[tuple[str, str]] = []
        for source in recent_selected:
            surfaced_entries.append(
                (
                    source.note_path,
                    _daily_recent_reason(
                        source,
                        theme_counts=theme_counts,
                        preference_profile=preference_profile,
                    ),
                )
            )
        if resurfaced_source is not None:
            included_sources.append(resurfaced_source)
            surfaced_entries.append(
                (
                    resurfaced_source.note_path,
                    _daily_resurface_reason(
                        resurfaced_source,
                        theme_counts=theme_counts,
                        last_surfaced_at=last_surface.get(resurfaced_source.note_path),
                        reference=period_start,
                        preference_profile=preference_profile,
                    ),
                )
            )

        report = _render_daily_digest(
            target_date=target_date,
            recent_selected=recent_selected,
            resurfaced_source=resurfaced_source,
            theme_counts=theme_counts,
            last_surface=last_surface,
            preference_profile=preference_profile,
        )
        saved_to = _save_digest(
            vault_path=vault_path,
            output_path=output_path,
            review_type="daily",
            period_key=period_key,
            report=report,
            included_sources=included_sources,
            resurfaced_sources=[resurfaced_source] if resurfaced_source else [],
            extra_meta={"active_theme_preferences": preference_profile.active_themes},
        )
        history_repo.replace_period_entries(
            review_type="daily",
            period_key=period_key,
            surfaced_at=utcnow(),
            entries=surfaced_entries,
        )
        return ReviewDigestResult(
            review_type="daily",
            period_key=period_key,
            digest_status="published",
            report=report,
            source_references=[source.note_path for source in included_sources],
            resurfaced_references=[resurfaced_source.note_path] if resurfaced_source else [],
            source_count=len(included_sources),
            saved_to=saved_to,
            confidence=_daily_confidence(recent_selected=recent_selected),
        )
    finally:
        db.close()


async def generate_weekly_digest(
    *,
    reference_date: date | None = None,
) -> ReviewDigestResult:
    target_date = reference_date or utcnow().date()
    settings = get_settings()
    vault_path = Path(settings.vault_path)
    db = Database(settings.db_path)
    db.connect()

    try:
        history_repo = ReviewSurfaceHistoryRepository(db)
        iso_year, iso_week, _ = target_date.isocalendar()
        period_key = f"{iso_year}-W{iso_week:02d}"
        output_path = weekly_digest_output_path(vault_path, period_key)
        week_start = date.fromisocalendar(iso_year, iso_week, 1)
        week_start_dt = _day_start(week_start)
        week_end_dt = week_start_dt + timedelta(days=7)

        sources = _load_sources(vault_path)
        eligible_sources = [
            source for source in sources if source.is_usable and not source.review_excluded
        ]
        corpus_theme_counts = _theme_counts(eligible_sources)
        week_sources = [
            source
            for source in eligible_sources
            if week_start_dt <= source.saved_at < week_end_dt
        ]
        week_theme_counts = _theme_counts(week_sources)
        recurring_themes = _recurring_themes(week_theme_counts, corpus_theme_counts)
        preference_profile = _build_preference_profile(
            sources=eligible_sources,
            history_rows=history_repo.list_surfaces_since(
                since=week_start_dt - timedelta(days=21),
                exclude_period_key=period_key,
            ),
        )
        highlights = sorted(
            week_sources,
            key=lambda source: _weekly_highlight_rank(
                source,
                week_theme_counts=week_theme_counts,
                corpus_theme_counts=corpus_theme_counts,
                preference_profile=preference_profile,
            ),
        )[:5]
        topic_candidates = _topic_bundle_candidates(
            recurring_themes=recurring_themes,
            corpus_theme_counts=corpus_theme_counts,
            week_theme_counts=week_theme_counts,
        )

        published, skip_reason = _weekly_publish_decision(
            week_sources=week_sources,
            recurring_themes=recurring_themes,
        )
        if not published:
            history_repo.clear_period(review_type="weekly", period_key=period_key)
            if output_path.exists():
                output_path.unlink()
            return ReviewDigestResult(
                review_type="weekly",
                period_key=period_key,
                digest_status="skipped",
                reason=skip_reason,
            )

        report = _render_weekly_digest(
            period_key=period_key,
            highlights=highlights,
            recurring_themes=recurring_themes,
            topic_candidates=topic_candidates,
            week_theme_counts=week_theme_counts,
            corpus_theme_counts=corpus_theme_counts,
            preference_profile=preference_profile,
        )
        saved_to = _save_digest(
            vault_path=vault_path,
            output_path=output_path,
            review_type="weekly",
            period_key=period_key,
            report=report,
            included_sources=highlights,
            resurfaced_sources=[],
            extra_meta={
                "period_source_count": len(week_sources),
                "recurring_themes": recurring_themes,
                "topic_bundle_candidates": topic_candidates,
                "active_theme_preferences": preference_profile.active_themes,
            },
        )
        history_repo.replace_period_entries(
            review_type="weekly",
            period_key=period_key,
            surfaced_at=utcnow(),
            entries=[
                (
                    source.note_path,
                    _weekly_highlight_reason(
                        source,
                        week_theme_counts=week_theme_counts,
                        corpus_theme_counts=corpus_theme_counts,
                        preference_profile=preference_profile,
                    ),
                )
                for source in highlights
            ],
        )
        return ReviewDigestResult(
            review_type="weekly",
            period_key=period_key,
            digest_status="published",
            report=report,
            source_references=[source.note_path for source in highlights],
            source_count=len(highlights),
            saved_to=saved_to,
            confidence=_weekly_confidence(
                highlight_count=len(highlights),
                recurring_theme_count=len(recurring_themes),
            ),
        )
    finally:
        db.close()


def _load_sources(vault_path: Path) -> list[ReviewSource]:
    sources: list[ReviewSource] = []
    for note in scan_vault(vault_path):
        if note.note_type != "source":
            continue
        source = _review_source_from_note(note)
        if source is not None:
            sources.append(source)
    return sources


def _review_source_from_note(note: VaultNote) -> ReviewSource | None:
    brief_status = str(note.meta.get("brief_status", "partial") or "partial").strip().lower()
    if brief_status == "failed":
        return None

    saved_at = _parse_dt(str(note.meta.get("saved_at", "") or "").strip())
    if saved_at is None:
        saved_at = datetime.fromtimestamp(note.path.stat().st_mtime, tz=timezone.utc)

    user_state = note.meta.get("user_state", {}) or {}
    review_excluded = bool(user_state.get("review_excluded", False))
    theme_tags = [
        str(tag).strip()
        for tag in note.meta.get("theme_tags", []) or []
        if str(tag).strip()
    ]
    quick_summary = str(note.meta.get("quick_summary", "") or "").strip() or _body_summary(note.body)
    best_next_action = str(note.meta.get("best_next_action", "") or "").strip()
    if not best_next_action:
        best_next_action = str(note.meta.get("consume_recommendation", "") or "").strip()

    lifecycle = dict(note.meta.get("lifecycle", {}) or {})
    confidence_raw = lifecycle.get("confidence")
    lifecycle_confidence = (
        float(confidence_raw) if isinstance(confidence_raw, (int, float)) else None
    )
    reinforcement_raw = lifecycle.get("reinforcement_count", 0)
    reinforcement_count = (
        int(reinforcement_raw) if isinstance(reinforcement_raw, (int, float)) else 0
    )

    return ReviewSource(
        note_path=note.rel_path,
        title=note.title,
        source_type=str(note.meta.get("source_type", "") or "").strip() or "unknown",
        brief_status=brief_status,
        reading_state=str(note.meta.get("reading_state", "") or "").strip().lower(),
        theme_tags=theme_tags,
        quick_summary=quick_summary or "No quick summary available.",
        best_next_action=best_next_action
        or "Use the brief first, then open the original only if you need more depth.",
        why_it_matters=str(note.meta.get("why_it_matters", "") or "").strip(),
        saved_at=saved_at,
        review_excluded=review_excluded,
        lifecycle_confidence=lifecycle_confidence,
        lifecycle_last_confirmed_at=_parse_dt(
            str(lifecycle.get("last_confirmed_at", "") or "").strip()
        ),
        lifecycle_staleness_status=str(
            lifecycle.get("staleness_status", StalenessStatus.UNKNOWN) or StalenessStatus.UNKNOWN
        ).strip().lower(),
        reinforcement_count=max(0, reinforcement_count),
    )


def _body_summary(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith(">"):
            return stripped[:220]
    return ""


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


def _day_start(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _theme_counts(sources: list[ReviewSource]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for source in sources:
        for tag in source.theme_tags:
            counts[tag] += 1
    return counts


def _build_preference_profile(
    *,
    sources: list[ReviewSource],
    history_rows: list[dict[str, str]],
) -> PreferenceProfile:
    affinity: Counter[str] = Counter()
    source_index = {source.note_path: source for source in sources}

    for source in sources:
        weight = {
            "up_next": 4,
            "review": 3,
            "queued": 1,
        }.get(source.reading_state, 0)
        if weight <= 0:
            continue
        for tag in source.theme_tags:
            affinity[tag] += weight

    for row in history_rows:
        source = source_index.get(str(row.get("source_note_path", "") or ""))
        if source is None:
            continue
        for tag in source.theme_tags:
            affinity[tag] += 1

    return PreferenceProfile(theme_affinity=affinity)


def _reading_state_rank(source: ReviewSource) -> int:
    return {
        "up_next": 0,
        "review": 1,
        "queued": 2,
        "brief_may_be_enough": 3,
    }.get(source.reading_state, 4)


def _brief_rank(source: ReviewSource) -> int:
    return 0 if source.is_ready else 1


def _lifecycle_staleness_rank(source: ReviewSource) -> int:
    return {
        StalenessStatus.STALE: 0,
        StalenessStatus.NEEDS_REVIEW: 1,
        StalenessStatus.UNKNOWN: 2,
        StalenessStatus.CURRENT: 3,
    }.get(source.lifecycle_staleness_status, 2)


def _theme_weight(source: ReviewSource, theme_counts: Counter[str]) -> int:
    if not source.theme_tags:
        return 0
    return max(theme_counts.get(tag, 0) for tag in source.theme_tags)


def _preference_weight(source: ReviewSource, preference_profile: PreferenceProfile) -> int:
    if not source.theme_tags:
        return 0
    return max(preference_profile.theme_affinity.get(tag, 0) for tag in source.theme_tags)


def _daily_recent_rank(
    source: ReviewSource,
    *,
    theme_counts: Counter[str],
    preference_profile: PreferenceProfile,
) -> tuple[int, int, int, int, float, str]:
    return (
        _brief_rank(source),
        _reading_state_rank(source),
        -_preference_weight(source, preference_profile),
        -_theme_weight(source, theme_counts),
        -source.saved_at.timestamp(),
        source.title.lower(),
    )


def _choose_resurfaced_source(
    *,
    sources: list[ReviewSource],
    theme_counts: Counter[str],
    last_surface: dict[str, datetime],
    period_start: datetime,
    already_selected: set[str],
    preference_profile: PreferenceProfile,
) -> ReviewSource | None:
    candidates = [
        source
        for source in sources
        if source.note_path not in already_selected
        and source.saved_at <= period_start - timedelta(days=7)
        and not _surfaced_within(last_surface.get(source.note_path), period_start, days=14)
    ]
    if not candidates:
        return None
    ranked = sorted(
        candidates,
        key=lambda source: _resurface_rank(
            source,
            theme_counts=theme_counts,
            last_surfaced_at=last_surface.get(source.note_path),
            period_start=period_start,
            preference_profile=preference_profile,
        ),
    )
    return ranked[0]


def _resurface_rank(
    source: ReviewSource,
    *,
    theme_counts: Counter[str],
    last_surfaced_at: datetime | None,
    period_start: datetime,
    preference_profile: PreferenceProfile,
) -> tuple[int, int, int, int, int, int, int, str]:
    if last_surfaced_at is None:
        days_since_surface = 3650
    else:
        days_since_surface = max(0, int((period_start - last_surfaced_at).total_seconds() // 86400))
    age_days = max(0, int((period_start - source.saved_at).total_seconds() // 86400))
    lifecycle_days = max(
        0,
        int(
            (
                period_start - (source.lifecycle_last_confirmed_at or source.saved_at)
            ).total_seconds()
            // 86400
        ),
    )
    return (
        _brief_rank(source),
        _lifecycle_staleness_rank(source),
        _reading_state_rank(source),
        -_preference_weight(source, preference_profile),
        -_theme_weight(source, theme_counts),
        source.reinforcement_count,
        -max(days_since_surface, lifecycle_days),
        source.title.lower(),
    )


def _surfaced_within(last_surfaced_at: datetime | None, reference: datetime, *, days: int) -> bool:
    if last_surfaced_at is None:
        return False
    return last_surfaced_at >= reference - timedelta(days=days)


def _last_surface_map(rows: list[dict[str, str]]) -> dict[str, datetime]:
    result: dict[str, datetime] = {}
    for row in rows:
        note_path = str(row.get("source_note_path", "") or "")
        surfaced_at = _parse_dt(str(row.get("surfaced_at", "") or "").strip())
        if note_path and surfaced_at is not None and note_path not in result:
            result[note_path] = surfaced_at
    return result


def _daily_publish_decision(
    *,
    recent_selected: list[ReviewSource],
    resurfaced_source: ReviewSource | None,
) -> tuple[bool, str]:
    ready_recent = sum(1 for source in recent_selected if source.is_ready)
    signal_score = (ready_recent * 2) + (len(recent_selected) - ready_recent)
    if resurfaced_source is not None:
        signal_score += 2 if resurfaced_source.is_ready else 1
    if signal_score >= 4:
        return True, ""
    return False, "Not enough signal for a useful daily review yet."


def _daily_recent_reason(
    source: ReviewSource,
    *,
    theme_counts: Counter[str],
    preference_profile: PreferenceProfile,
) -> str:
    parts: list[str] = []
    parts.append("ready brief" if source.is_ready else "usable partial brief")
    if source.reading_state:
        parts.append(source.reading_state.replace("_", " "))
    if source.preferred_theme and _preference_weight(source, preference_profile) > 0:
        parts.append(f"matches current focus: {source.preferred_theme}")
    if source.theme_tags:
        tag = source.theme_tags[0]
        if theme_counts.get(tag, 0) >= 2:
            parts.append(f"recurring {tag} theme")
    parts.append(f"{source.source_type} source")
    return ", ".join(parts[:4])


def _daily_resurface_reason(
    source: ReviewSource,
    *,
    theme_counts: Counter[str],
    last_surfaced_at: datetime | None,
    reference: datetime,
    preference_profile: PreferenceProfile,
) -> str:
    parts: list[str] = []
    age_days = max(0, int((reference - source.saved_at).total_seconds() // 86400))
    parts.append(f"{age_days} days old")
    lifecycle_reason = _lifecycle_reason(source, reference=reference)
    if lifecycle_reason:
        parts.append(lifecycle_reason)
    if last_surfaced_at is None:
        parts.append("not surfaced recently")
    else:
        gap_days = max(0, int((reference - last_surfaced_at).total_seconds() // 86400))
        parts.append(f"last surfaced {gap_days} days ago")
    if source.preferred_theme and _preference_weight(source, preference_profile) > 0:
        parts.append(f"still aligned with focus: {source.preferred_theme}")
    if source.theme_tags:
        tag = source.theme_tags[0]
        if theme_counts.get(tag, 0) >= 2:
            parts.append(f"theme still active: {tag}")
    return ", ".join(parts[:5])


def _lifecycle_reason(source: ReviewSource, *, reference: datetime) -> str:
    if source.lifecycle_staleness_status == StalenessStatus.STALE:
        return "marked stale"
    if source.lifecycle_staleness_status == StalenessStatus.NEEDS_REVIEW:
        return "marked needs review"
    if source.reinforcement_count <= 1:
        return "lightly reinforced"
    if source.lifecycle_last_confirmed_at is not None:
        days = max(
            0,
            int((reference - source.lifecycle_last_confirmed_at).total_seconds() // 86400),
        )
        if days >= 21:
            return f"not confirmed for {days} days"
    return ""


def _daily_next_step(
    recent_selected: list[ReviewSource],
    resurfaced_source: ReviewSource | None,
) -> str:
    included = list(recent_selected)
    if resurfaced_source is not None:
        included.append(resurfaced_source)

    theme_counter: Counter[str] = Counter()
    for source in included:
        for tag in source.theme_tags:
            theme_counter[tag] += 1

    if theme_counter:
        theme, count = theme_counter.most_common(1)[0]
        lead = included[0]
        if count >= 2:
            return (
                f"Stay on `{theme}` next. Start with {lead.title}, then only open the original "
                "sources if the brief leaves a gap."
            )

    if recent_selected:
        return recent_selected[0].best_next_action
    if resurfaced_source is not None:
        return resurfaced_source.best_next_action
    return "Wait for more ready briefs before publishing a review."


def _render_daily_digest(
    *,
    target_date: date,
    recent_selected: list[ReviewSource],
    resurfaced_source: ReviewSource | None,
    theme_counts: Counter[str],
    last_surface: dict[str, datetime],
    preference_profile: PreferenceProfile,
) -> str:
    lines = [
        f"# Daily Review: {target_date.isoformat()}",
        "",
        "> Question: What is worth your attention today?",
        f"> Generated: {friendly_date()}",
        "",
    ]

    if preference_profile.active_themes:
        lines.extend(
            [
                "## Current Focus",
                "",
                (
                    "- Active themes from recent reading-state and review history: "
                    + ", ".join(f"`{theme}`" for theme in preference_profile.active_themes)
                ),
                "",
            ]
        )

    lines.extend(
        [
            "## Worth Looking At Today",
            "",
        ]
    )

    for source in recent_selected:
        lines.extend(
            [
                f"### {path_wikilink(source.note_path, source.title)}",
                "",
                (
                    "- **Why now:** "
                    + _daily_recent_reason(
                        source,
                        theme_counts=theme_counts,
                        preference_profile=preference_profile,
                    )
                ),
                f"- **Quick summary:** {source.quick_summary}",
                f"- **Best next action:** {source.best_next_action}",
                "",
            ]
        )

    if resurfaced_source is not None:
        lines.extend(
            [
                "## One Older Item To Revisit",
                "",
                f"### {path_wikilink(resurfaced_source.note_path, resurfaced_source.title)}",
                "",
                (
                    "- **Why resurface this now:** "
                    + _daily_resurface_reason(
                        resurfaced_source,
                        theme_counts=theme_counts,
                        last_surfaced_at=last_surface.get(resurfaced_source.note_path),
                        reference=_day_start(target_date),
                        preference_profile=preference_profile,
                    )
                ),
                f"- **Quick summary:** {resurfaced_source.quick_summary}",
                f"- **Best next action:** {resurfaced_source.best_next_action}",
                "",
            ]
        )

    lines.extend(
        [
            "## Concrete Next Step",
            "",
            f"- {_daily_next_step(recent_selected, resurfaced_source)}",
        ]
    )
    return "\n".join(lines).strip()


def _daily_confidence(*, recent_selected: list[ReviewSource]) -> str:
    ready_count = sum(1 for source in recent_selected if source.is_ready)
    if ready_count >= 2:
        return "high"
    if ready_count >= 1:
        return "medium"
    return "low"


def _weekly_highlight_rank(
    source: ReviewSource,
    *,
    week_theme_counts: Counter[str],
    corpus_theme_counts: Counter[str],
    preference_profile: PreferenceProfile,
) -> tuple[int, int, int, int, int, float, str]:
    week_weight = _theme_weight(source, week_theme_counts)
    corpus_weight = _theme_weight(source, corpus_theme_counts)
    return (
        _brief_rank(source),
        _reading_state_rank(source),
        -_preference_weight(source, preference_profile),
        -week_weight,
        -corpus_weight,
        -source.saved_at.timestamp(),
        source.title.lower(),
    )


def _weekly_publish_decision(
    *,
    week_sources: list[ReviewSource],
    recurring_themes: list[str],
) -> tuple[bool, str]:
    ready_count = sum(1 for source in week_sources if source.is_ready)
    if len(week_sources) >= 3:
        return True, ""
    if ready_count >= 2 and recurring_themes:
        return True, ""
    return False, "Not enough weekly signal to justify a digest."


def _recurring_themes(
    week_theme_counts: Counter[str],
    corpus_theme_counts: Counter[str],
) -> list[str]:
    themes = [theme for theme, count in week_theme_counts.items() if count >= 2]
    return sorted(
        themes,
        key=lambda theme: (
            -week_theme_counts[theme],
            -corpus_theme_counts[theme],
            theme,
        ),
    )[:4]


def _topic_bundle_candidates(
    *,
    recurring_themes: list[str],
    corpus_theme_counts: Counter[str],
    week_theme_counts: Counter[str],
) -> list[str]:
    return [
        theme
        for theme in recurring_themes
        if corpus_theme_counts.get(theme, 0) >= 3 or week_theme_counts.get(theme, 0) >= 3
    ][:3]


def _weekly_highlight_reason(
    source: ReviewSource,
    *,
    week_theme_counts: Counter[str],
    corpus_theme_counts: Counter[str],
    preference_profile: PreferenceProfile,
) -> str:
    parts: list[str] = []
    parts.append("ready brief" if source.is_ready else "usable partial brief")
    if source.preferred_theme and _preference_weight(source, preference_profile) > 0:
        parts.append(f"matches current focus: {source.preferred_theme}")
    if source.theme_tags:
        tag = source.theme_tags[0]
        parts.append(f"{week_theme_counts.get(tag, 0)} saves on {tag} this week")
        if corpus_theme_counts.get(tag, 0) > week_theme_counts.get(tag, 0):
            parts.append(f"{corpus_theme_counts.get(tag, 0)} total in corpus")
    lifecycle_reason = _lifecycle_reason(source, reference=utcnow())
    if lifecycle_reason:
        parts.append(lifecycle_reason)
    return ", ".join(parts[:4])


def _deeper_study_line(
    *,
    recurring_themes: list[str],
    topic_candidates: list[str],
    highlights: list[ReviewSource],
) -> str:
    if topic_candidates:
        theme = topic_candidates[0]
        return (
            f"Go deeper on `{theme}` next. The pattern is now dense enough to justify a "
            "topic bundle."
        )
    if recurring_themes:
        return f"Stay with `{recurring_themes[0]}` and compare the top two briefs side by side."
    if highlights:
        return highlights[0].best_next_action
    return "No deeper-study direction is available yet."


def _render_weekly_digest(
    *,
    period_key: str,
    highlights: list[ReviewSource],
    recurring_themes: list[str],
    topic_candidates: list[str],
    week_theme_counts: Counter[str],
    corpus_theme_counts: Counter[str],
    preference_profile: PreferenceProfile,
) -> str:
    lines = [
        f"# Weekly Review: {period_key}",
        "",
        "> Question: What patterns are forming, and where should you go deeper next?",
        f"> Generated: {friendly_date()}",
        "",
    ]

    if preference_profile.active_themes:
        lines.extend(
            [
                "## Current Focus",
                "",
                (
                    "- Active themes from recent reading-state and review history: "
                    + ", ".join(f"`{theme}`" for theme in preference_profile.active_themes)
                ),
                "",
            ]
        )

    lines.extend(
        [
            "## Strongest Saves This Week",
            "",
        ]
    )

    for source in highlights:
        lines.extend(
            [
                f"### {path_wikilink(source.note_path, source.title)}",
                "",
                (
                    "- **Why it stood out:** "
                    + _weekly_highlight_reason(
                        source,
                        week_theme_counts=week_theme_counts,
                        corpus_theme_counts=corpus_theme_counts,
                        preference_profile=preference_profile,
                    )
                ),
                f"- **Quick summary:** {source.quick_summary}",
                f"- **Best next action:** {source.best_next_action}",
                "",
            ]
        )

    lines.extend(["## Patterns Forming", ""])
    if not recurring_themes:
        lines.append("- No strong repeated theme emerged this week.")
    else:
        for theme in recurring_themes:
            lines.append(
                f"- `{theme}` appeared in {week_theme_counts.get(theme, 0)} weekly saves "
                f"and {corpus_theme_counts.get(theme, 0)} corpus sources."
            )

    lines.extend(
        [
            "",
            "## Where To Go Deeper Next",
            "",
            (
                f"- {_deeper_study_line(recurring_themes=recurring_themes, topic_candidates=topic_candidates, highlights=highlights)}"
            ),
            "",
            "## Candidate Topic Bundles",
            "",
        ]
    )
    if not topic_candidates:
        lines.append("- No bundle candidate crossed the threshold this week.")
    else:
        for theme in topic_candidates:
            lines.append(
                f"- `{theme}` — enough repeated coverage is present to justify a topic bundle."
            )

    lines.extend(["", "## Included Sources", ""])
    for source in highlights:
        lines.append(f"- {path_wikilink(source.note_path, source.title)}")

    return "\n".join(lines).strip()


def _weekly_confidence(*, highlight_count: int, recurring_theme_count: int) -> str:
    if highlight_count >= 4 and recurring_theme_count >= 2:
        return "high"
    if highlight_count >= 2:
        return "medium"
    return "low"


def _save_digest(
    *,
    vault_path: Path,
    output_path: Path,
    review_type: str,
    period_key: str,
    report: str,
    included_sources: list[ReviewSource],
    resurfaced_sources: list[ReviewSource],
    extra_meta: dict[str, object],
) -> str:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "title": f"{review_type.capitalize()} Review: {period_key}",
        "type": "review_digest",
        "review_type": review_type,
        "period_key": period_key,
        "digest_status": "published",
        "generated_at": utcnow().isoformat(timespec="seconds"),
        "source_count": len(included_sources),
        "included_source_paths": [source.note_path for source in included_sources],
        "resurfaced_source_paths": [source.note_path for source in resurfaced_sources],
        **extra_meta,
    }
    output_path.write_text(build_frontmatter_doc(meta, report.strip()), encoding="utf-8")
    rel_path = str(output_path.relative_to(vault_path))
    publish(
        EventType.REVIEW_DIGEST_SAVED,
        review_type=review_type,
        period_key=period_key,
        saved_to=rel_path,
        source_references=[source.note_path for source in included_sources],
    )
    return rel_path
