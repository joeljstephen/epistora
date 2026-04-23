from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from app.cli.main import app as cli_app
from app.events import EventType, clear_subscribers, subscribe
from app.storage.repositories import ReviewSurfaceHistoryRepository
from app.storage.sqlite import Database
from app.utils.markdown import build_frontmatter_doc, parse_frontmatter
from app.vault.writer import VaultWriter

runner = CliRunner()


def setup_function():
    clear_subscribers()


def teardown_function():
    clear_subscribers()


def _source_paths(source_type: str, slug: str) -> tuple[str, str]:
    if source_type == "youtube":
        return f"raw/videos/{slug}.md", f"wiki/sources/videos/{slug}.md"
    return f"raw/articles/{slug}.md", f"wiki/sources/articles/{slug}.md"


def _write_source(
    writer: VaultWriter,
    vault: Path,
    *,
    slug: str,
    title: str,
    source_type: str,
    url: str,
    saved_at: datetime,
    theme_tags: list[str],
    brief_status: str = "ready",
    review_excluded: bool = False,
    reading_state: str | None = None,
    lifecycle: dict | None = None,
) -> str:
    from app.models.lifecycle import LifecycleMetadata
    from app.models.source import SourceContent, SourceItem, SourceType

    item = SourceItem(
        url=url,
        title=title,
        source_type=SourceType(source_type),
        saved_at=saved_at,
    )
    content = SourceContent(
        source=item,
        raw_text=f"Raw capture for {title}",
        cleaned_text=f"Compiled details for {title}",
        word_count=120,
        extraction_quality="full" if brief_status == "ready" else "partial",
        content_hash=f"{slug}-hash",
        url_hash=f"{slug}-url-hash",
        author="Author",
        lifecycle=LifecycleMetadata(**(lifecycle or {})),
    )
    raw_path, source_path = _source_paths(source_type, slug)
    writer.write_raw_capture(content, slug)
    writer.write_source_note(
        content=content,
        slug=slug,
        raw_capture_path=raw_path,
        quick_brief=f"Quick brief for {title}",
        summary=f"Summary of {title}",
        five_minute_read=f"Briefing for {title}",
        detailed_reading_note=f"Detailed note for {title}",
        best_next_action=f"Start with {title}.",
        theme_tags=theme_tags,
        brief_status=brief_status,
        watch_verdict="Worth watching selectively." if source_type == "youtube" else "",
        watch_verdict_reasoning="The useful sections are already captured."
        if source_type == "youtube"
        else "",
        quick_section_guide="- Section 1" if source_type == "youtube" else "",
        detailed_sections="### Section 1\nDetail" if source_type == "youtube" else "",
        signal_vs_filler="- Mostly signal" if source_type == "youtube" else "",
        important_terms="- Agent\n- Workflow",
        key_ideas=f"- Key point about {title}",
        detailed_outline=f"## Overview of {title}",
        important_examples=f"- Example from {title}",
        actionable_takeaways=f"- Apply ideas from {title}",
        notable_quotes="- None captured verbatim.",
        best_for=f"- Readers learning about {title}",
        consume_recommendation=f"Open {title} only if you need more depth.",
        why_it_matters=f"{title} matters in the vault.",
        open_questions=f"- More to explore about {title}",
        topics=["Agent Workflows"],
        entities=[],
        concepts=["Agent Workflow"],
    )

    abs_source_path = vault / source_path
    if review_excluded or reading_state:
        meta, body = parse_frontmatter(abs_source_path.read_text(encoding="utf-8"))
        user_state = dict(meta.get("user_state", {}) or {})
        if review_excluded:
            user_state["review_excluded"] = True
        if reading_state:
            user_state["reading_state"] = reading_state
            meta["reading_state"] = reading_state
        meta["user_state"] = user_state
        abs_source_path.write_text(build_frontmatter_doc(meta, body), encoding="utf-8")
    return source_path


def _settings_for(vault: Path):
    return type("Settings", (), {"vault_path": vault, "db_path": vault.parent / "review.db"})()


def test_generate_daily_digest_publishes_and_records_history(tmp_vault: Path):
    from app.services.review_service import generate_daily_digest

    writer = VaultWriter(tmp_vault)
    day = datetime(2026, 4, 21, 12, tzinfo=timezone.utc)
    _write_source(
        writer,
        tmp_vault,
        slug="recent-one",
        title="Recent One",
        source_type="article",
        url="https://example.com/recent-one",
        saved_at=day - timedelta(hours=5),
        theme_tags=["agentic-ai"],
    )
    _write_source(
        writer,
        tmp_vault,
        slug="recent-two",
        title="Recent Two",
        source_type="article",
        url="https://example.com/recent-two",
        saved_at=day - timedelta(days=1),
        theme_tags=["agentic-ai"],
    )
    older_path = _write_source(
        writer,
        tmp_vault,
        slug="older-video",
        title="Older Video",
        source_type="youtube",
        url="https://example.com/older-video",
        saved_at=day - timedelta(days=16),
        theme_tags=["agentic-ai"],
    )

    events = []
    subscribe(EventType.REVIEW_DIGEST_SAVED, events.append)

    with patch("app.services.review_service.get_settings", return_value=_settings_for(tmp_vault)):
        import asyncio

        result = asyncio.run(generate_daily_digest(reference_date=date(2026, 4, 21)))

    assert result.digest_status == "published"
    assert result.saved_to == "outputs/digests/daily/2026-04-21.md"
    assert result.resurfaced_references == [older_path]
    saved_path = tmp_vault / result.saved_to
    assert saved_path.exists()
    saved_text = saved_path.read_text(encoding="utf-8")
    assert "review_type: daily" in saved_text
    assert "included_source_paths:" in saved_text
    assert "What is worth your attention today?" in saved_text
    assert "One Older Item To Revisit" in saved_text

    db = Database(_settings_for(tmp_vault).db_path)
    db.connect()
    try:
        history_rows = ReviewSurfaceHistoryRepository(db).list_surfaces_since(
            since=datetime(2026, 4, 1, tzinfo=timezone.utc)
        )
    finally:
        db.close()

    assert len(history_rows) == 3
    assert len(events) == 1
    assert events[0].payload["review_type"] == "daily"


def test_generate_daily_digest_skips_when_signal_is_too_thin(tmp_vault: Path):
    from app.services.review_service import generate_daily_digest

    writer = VaultWriter(tmp_vault)
    _write_source(
        writer,
        tmp_vault,
        slug="single-recent",
        title="Single Recent",
        source_type="article",
        url="https://example.com/single-recent",
        saved_at=datetime(2026, 4, 21, 10, tzinfo=timezone.utc),
        theme_tags=["career"],
    )

    with patch("app.services.review_service.get_settings", return_value=_settings_for(tmp_vault)):
        import asyncio

        result = asyncio.run(generate_daily_digest(reference_date=date(2026, 4, 21)))

    assert result.digest_status == "skipped"
    assert result.saved_to is None
    assert "Not enough signal" in result.reason
    assert not (tmp_vault / "outputs/digests/daily/2026-04-21.md").exists()


def test_daily_resurfacing_respects_anti_repetition_window(tmp_vault: Path):
    from app.services.review_service import generate_daily_digest

    writer = VaultWriter(tmp_vault)
    day = datetime(2026, 4, 21, 12, tzinfo=timezone.utc)
    for slug, title, saved_at in (
        ("recent-a", "Recent A", day - timedelta(hours=3)),
        ("recent-b", "Recent B", day - timedelta(days=1)),
    ):
        _write_source(
            writer,
            tmp_vault,
            slug=slug,
            title=title,
            source_type="article",
            url=f"https://example.com/{slug}",
            saved_at=saved_at,
            theme_tags=["agentic-ai"],
        )

    first_old = _write_source(
        writer,
        tmp_vault,
        slug="old-a",
        title="Old A",
        source_type="article",
        url="https://example.com/old-a",
        saved_at=day - timedelta(days=20),
        theme_tags=["agentic-ai"],
    )
    second_old = _write_source(
        writer,
        tmp_vault,
        slug="old-b",
        title="Old B",
        source_type="article",
        url="https://example.com/old-b",
        saved_at=day - timedelta(days=18),
        theme_tags=["agentic-ai"],
    )

    with patch("app.services.review_service.get_settings", return_value=_settings_for(tmp_vault)):
        import asyncio

        first = asyncio.run(generate_daily_digest(reference_date=date(2026, 4, 21)))
        second = asyncio.run(generate_daily_digest(reference_date=date(2026, 4, 22)))

    assert first.digest_status == "published"
    assert first.resurfaced_references == [first_old]
    assert second.digest_status == "published"
    assert second.resurfaced_references == [second_old]
    assert first_old not in second.resurfaced_references


def test_daily_resurfacing_prefers_lifecycle_attention_items(tmp_vault: Path):
    from app.services.review_service import generate_daily_digest

    writer = VaultWriter(tmp_vault)
    day = datetime(2026, 4, 21, 12, tzinfo=timezone.utc)
    for slug, title, saved_at in (
        ("recent-focus-a", "Recent Focus A", day - timedelta(hours=4)),
        ("recent-focus-b", "Recent Focus B", day - timedelta(days=1)),
    ):
        _write_source(
            writer,
            tmp_vault,
            slug=slug,
            title=title,
            source_type="article",
            url=f"https://example.com/{slug}",
            saved_at=saved_at,
            theme_tags=["agentic-ai"],
        )

    stale_old = _write_source(
        writer,
        tmp_vault,
        slug="stale-old",
        title="Stale Old",
        source_type="article",
        url="https://example.com/stale-old",
        saved_at=day - timedelta(days=20),
        theme_tags=["agentic-ai"],
        lifecycle={
            "staleness_status": "needs_review",
            "last_confirmed_at": (day - timedelta(days=45)).isoformat(),
            "reinforcement_count": 1,
        },
    )
    current_old = _write_source(
        writer,
        tmp_vault,
        slug="current-old",
        title="Current Old",
        source_type="article",
        url="https://example.com/current-old",
        saved_at=day - timedelta(days=25),
        theme_tags=["agentic-ai"],
        lifecycle={
            "staleness_status": "current",
            "last_confirmed_at": (day - timedelta(days=3)).isoformat(),
            "reinforcement_count": 4,
        },
    )

    with patch("app.services.review_service.get_settings", return_value=_settings_for(tmp_vault)):
        import asyncio

        result = asyncio.run(generate_daily_digest(reference_date=date(2026, 4, 21)))

    assert result.digest_status == "published"
    assert result.resurfaced_references == [stale_old]
    assert current_old not in result.resurfaced_references
    saved_text = (tmp_vault / result.saved_to).read_text(encoding="utf-8")
    assert "marked needs review" in saved_text or "lightly reinforced" in saved_text


def test_daily_digest_uses_current_focus_preferences(tmp_vault: Path):
    from app.services.review_service import generate_daily_digest

    writer = VaultWriter(tmp_vault)
    day = datetime(2026, 4, 21, 12, tzinfo=timezone.utc)
    _write_source(
        writer,
        tmp_vault,
        slug="focus-anchor",
        title="Focus Anchor",
        source_type="article",
        url="https://example.com/focus-anchor",
        saved_at=day - timedelta(days=10),
        theme_tags=["career"],
        reading_state="up_next",
    )
    _write_source(
        writer,
        tmp_vault,
        slug="focus-recent",
        title="Focus Recent",
        source_type="article",
        url="https://example.com/focus-recent",
        saved_at=day - timedelta(hours=2),
        theme_tags=["career"],
    )
    _write_source(
        writer,
        tmp_vault,
        slug="other-recent",
        title="Other Recent",
        source_type="article",
        url="https://example.com/other-recent",
        saved_at=day - timedelta(hours=1),
        theme_tags=["self-hosted"],
    )

    with patch("app.services.review_service.get_settings", return_value=_settings_for(tmp_vault)):
        import asyncio

        result = asyncio.run(generate_daily_digest(reference_date=date(2026, 4, 21)))

    assert result.digest_status == "published"
    saved_text = (tmp_vault / result.saved_to).read_text(encoding="utf-8")
    assert "## Current Focus" in saved_text
    assert "`career`" in saved_text
    assert "matches current focus: career" in saved_text


def test_generate_weekly_digest_publishes_patterns_and_candidates(tmp_vault: Path):
    from app.services.review_service import generate_weekly_digest

    writer = VaultWriter(tmp_vault)
    base = datetime(2026, 4, 21, 12, tzinfo=timezone.utc)
    for slug, title, delta_days in (
        ("week-one", "Week One", 0),
        ("week-two", "Week Two", 1),
        ("week-three", "Week Three", 2),
    ):
        _write_source(
            writer,
            tmp_vault,
            slug=slug,
            title=title,
            source_type="article",
            url=f"https://example.com/{slug}",
            saved_at=base - timedelta(days=delta_days),
            theme_tags=["agentic-ai"],
        )

    with patch("app.services.review_service.get_settings", return_value=_settings_for(tmp_vault)):
        import asyncio

        result = asyncio.run(generate_weekly_digest(reference_date=date(2026, 4, 21)))

    assert result.digest_status == "published"
    assert result.saved_to == "outputs/digests/weekly/2026-W17.md"
    saved_text = (tmp_vault / result.saved_to).read_text(encoding="utf-8")
    assert "review_type: weekly" in saved_text
    assert "Patterns Forming" in saved_text
    assert "Candidate Topic Bundles" in saved_text
    assert "`agentic-ai`" in saved_text


def test_review_cli_commands_run(tmp_vault: Path):
    writer = VaultWriter(tmp_vault)
    day = datetime(2026, 4, 21, 12, tzinfo=timezone.utc)
    _write_source(
        writer,
        tmp_vault,
        slug="cli-one",
        title="CLI One",
        source_type="article",
        url="https://example.com/cli-one",
        saved_at=day - timedelta(hours=1),
        theme_tags=["career"],
    )
    _write_source(
        writer,
        tmp_vault,
        slug="cli-two",
        title="CLI Two",
        source_type="article",
        url="https://example.com/cli-two",
        saved_at=day - timedelta(days=1),
        theme_tags=["career"],
    )

    with patch("app.services.review_service.get_settings", return_value=_settings_for(tmp_vault)):
        result = runner.invoke(cli_app, ["review", "daily", "--date", "2026-04-21"])

    assert result.exit_code == 0
    assert "Review status:" in result.output
    assert "outputs/digests/daily/2026-04-21.md" in result.output


def test_review_api_routes_exist():
    from app.api.routes_review import router

    paths = {route.path for route in router.routes}
    assert "/review/daily" in paths
    assert "/review/weekly" in paths
