from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from app.cli.main import app as cli_app
from app.events import EventType, clear_subscribers, subscribe
from app.models.results import TopicBundleResult
from app.read_model import ReadModelStore
from app.vault.index_updater import rebuild_indexes
from app.vault.writer import VaultWriter

runner = CliRunner()


def setup_function():
    clear_subscribers()


def teardown_function():
    clear_subscribers()


def _write_source(
    writer: VaultWriter,
    *,
    slug: str,
    title: str,
    source_type: str,
    url: str,
    brief_status: str,
):
    from app.models.source import SourceContent, SourceItem, SourceType

    item = SourceItem(url=url, title=title, source_type=SourceType(source_type))
    content = SourceContent(
        source=item,
        raw_text=f"Raw content for {title}",
        cleaned_text=f"Compiled details for {title}.",
        word_count=12,
        extraction_quality="full" if brief_status == "ready" else "partial",
        content_hash=f"{slug}-hash",
        url_hash=f"{slug}-url-hash",
        author="Author",
    )
    writer.write_raw_capture(content, slug)
    writer.write_source_note(
        content=content,
        slug=slug,
        raw_capture_path=f"raw/articles/{slug}.md" if source_type == "article" else f"raw/videos/{slug}.md",
        quick_brief=f"Quick brief for {title}",
        summary=f"Summary of {title}",
        five_minute_read=f"Briefing for {title}",
        detailed_reading_note=f"Detailed note for {title}",
        best_next_action=f"Start with {title}.",
        theme_tags=["agentic-ai"],
        brief_status=brief_status,
        watch_verdict="Worth watching selectively." if source_type == "youtube" else "",
        watch_verdict_reasoning="Useful sections are captured in the brief."
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


def _seed_bundle_vault(tmp_vault: Path) -> Path:
    writer = VaultWriter(tmp_vault)
    _write_source(
        writer,
        slug="agent-overview",
        title="Agent Overview",
        source_type="article",
        url="https://example.com/agent-overview",
        brief_status="ready",
    )
    _write_source(
        writer,
        slug="agent-harness",
        title="Agent Harness Design",
        source_type="article",
        url="https://example.com/agent-harness",
        brief_status="ready",
    )
    _write_source(
        writer,
        slug="agent-video",
        title="Agent Harness Walkthrough",
        source_type="youtube",
        url="https://example.com/agent-video",
        brief_status="partial",
    )
    rebuild_indexes(tmp_vault)
    ReadModelStore(tmp_vault).rebuild()
    return tmp_vault


def test_generate_topic_bundle_saves_normal_bundle(tmp_vault: Path):
    from app.services.topic_bundle_service import generate_topic_bundle

    vault = _seed_bundle_vault(tmp_vault)
    events = []
    subscribe(EventType.TOPIC_BUNDLE_SAVED, events.append)

    async def fake_run_text(*args, **kwargs):
        return type(
            "Resp",
            (),
            {
                "success": True,
                "text": "## Topic Overview\nPacket\n\n## Why This Matters\nBecause\n\n## Best Sources To Start With\n- Agent Overview\n\n## What Each Source Contributed\n- Agent Overview\n\n## Agreements and Disagreements\n- None\n\n## Key Concepts / Terms\n- Agent Workflow\n\n## Recommended Order\n1. Agent Overview\n\n## If I Only Have 10 Minutes\n- Start with Agent Overview\n\n## Gaps / Missing Coverage\n- More examples\n\n## Included Sources\n- wiki/sources/articles/agent-overview.md",
                "error": "",
            },
        )()

    with patch("app.services.topic_bundle_service.get_settings") as mock_settings:
        mock_settings.return_value.vault_path = vault
        with patch("app.services.topic_bundle_service.run_text", new=fake_run_text):
            result = runner.invoke(
                cli_app,
                ["topic-bundle", "agent harness"],
            )

    assert result.exit_code == 0
    assert "Bundle status:" in result.output
    assert "normal" in result.output
    assert len(events) == 1
    saved_to = events[0].payload["saved_to"]
    assert saved_to.startswith("outputs/digests/topic-bundles/agent-harness--")
    saved_path = vault / saved_to
    assert saved_path.exists()
    saved_text = saved_path.read_text(encoding="utf-8")
    assert "bundle_status: normal" in saved_text
    assert "included_source_paths:" in saved_text


def test_generate_topic_bundle_returns_limited_bundle_for_sparse_filtered_set(tmp_vault: Path):
    from app.services.topic_bundle_service import generate_topic_bundle

    vault = _seed_bundle_vault(tmp_vault)

    with patch("app.services.topic_bundle_service.get_settings") as mock_settings:
        mock_settings.return_value.vault_path = vault
        async def fail_run_text(*args, **kwargs):
            raise RuntimeError("backend down")

        with patch("app.services.topic_bundle_service.run_text", new=fail_run_text):
            result = runner.invoke(
                cli_app,
                ["topic-bundle", "agent harness", "--source-types", "youtube"],
            )

    assert result.exit_code == 0
    assert "limited" in result.output
    saved_fragment = [
        line.split("Saved to:")[-1].strip()
        for line in result.output.splitlines()
        if "Saved to:" in line
    ][0]
    saved_text = (vault / saved_fragment).read_text(encoding="utf-8")
    assert "bundle_status: limited" in saved_text
    assert "Agent Harness Walkthrough" in saved_text


def test_topic_bundle_service_returns_model_result(tmp_vault: Path):
    from app.services.topic_bundle_service import generate_topic_bundle

    vault = _seed_bundle_vault(tmp_vault)

    async def fake_run_text(*args, **kwargs):
        return type("Resp", (), {"success": False, "text": "", "error": "backend unavailable"})()

    with patch("app.services.topic_bundle_service.get_settings") as mock_settings:
        mock_settings.return_value.vault_path = vault
        with patch("app.services.topic_bundle_service.run_text", new=fake_run_text):
            import asyncio

            result = asyncio.run(generate_topic_bundle("agent harness", source_types=["article"]))

    assert isinstance(result, TopicBundleResult)
    assert result.bundle_status == "limited"
    assert result.source_count == 2
    assert result.ready_source_count == 2
    assert result.saved_to is not None


def test_topic_bundle_cli_help_is_available():
    result = runner.invoke(cli_app, ["topic-bundle", "--help"])
    assert result.exit_code == 0
    assert "learning packet" in result.output.lower()


def test_topic_bundle_api_route_exists():
    from app.api.routes_topic_bundle import router

    route = router.routes[0]
    assert route.path == "/topic-bundle"
