from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.models.db import CatalogSource, ProcessedSource, SourceProviderRef
from app.storage.repositories import SourceCatalogRepository, SourceRepository
from app.storage.sqlite import Database


def test_studio_source_list_includes_metadata_only_rows(tmp_db):
    from app.services.studio_service import list_studio_sources

    repo = SourceCatalogRepository(tmp_db)
    repo.upsert_source(
        CatalogSource(
            url="https://example.com/catalog-only",
            title="Catalog Only",
            metadata_status="metadata_only",
            content_status="not_fetched",
        )
    )

    sources = list_studio_sources(tmp_db, query="catalog", metadata_only=True)

    assert len(sources) == 1
    assert sources[0].title == "Catalog Only"
    assert sources[0].display_state == "metadata_only"


def test_studio_source_detail_returns_refs_tags_and_latest_jobs(tmp_db):
    from app.services.studio_service import get_studio_source_detail

    repo = SourceCatalogRepository(tmp_db)
    source = repo.upsert_source(
        CatalogSource(url="https://example.com/detail", title="Detail Source")
    )
    repo.attach_provider_ref(
        SourceProviderRef(
            source_uid=source.uid,
            provider="raindrop",
            external_id="rd-1",
            external_url=source.url,
            metadata={"collection_id": 10},
        )
    )
    repo.sync_tags(source.uid, ["AI"], origin="provider")
    repo.enqueue_processing_job(
        source_uid=source.uid,
        task_type="capture",
        mode="safe",
        requested_by="studio",
    )

    detail = get_studio_source_detail(tmp_db, source.uid)

    assert detail is not None
    assert detail.uid == source.uid
    assert detail.provider_refs[0].provider == "raindrop"
    assert detail.tags[0].normalized_tag == "ai"
    assert detail.latest_jobs[0].task_type == "capture"


def test_studio_source_reader_returns_source_note_and_raw_capture(tmp_db, tmp_vault):
    from app.services.studio_service import get_studio_source_reader
    from app.utils.hashing import url_hash

    note_path = "wiki/sources/articles/readable.md"
    raw_path = "raw/articles/readable.md"
    (tmp_vault / "wiki" / "sources" / "articles").mkdir(parents=True, exist_ok=True)
    (tmp_vault / "raw" / "articles").mkdir(parents=True, exist_ok=True)
    (tmp_vault / note_path).write_text("# Readable Source\n\nCompiled note.", encoding="utf-8")
    (tmp_vault / raw_path).write_text("# Raw Capture\n\nRaw text.", encoding="utf-8")

    repo = SourceCatalogRepository(tmp_db)
    source = repo.upsert_source(
        CatalogSource(
            url="https://example.com/readable",
            title="Readable",
            url_hash=url_hash("https://example.com/readable"),
            metadata_status="captured",
            content_status="available",
        )
    )
    SourceRepository(tmp_db).upsert(
        ProcessedSource(
            url=source.url,
            url_hash=source.url_hash,
            title="Readable",
            source_note_path=note_path,
            raw_capture_path=raw_path,
            status="completed",
        )
    )

    reader = get_studio_source_reader(tmp_db, source.uid, vault_path=tmp_vault)

    assert reader is not None
    assert reader.has_source_note is True
    assert reader.has_raw_capture is True
    assert "Compiled note" in reader.source_markdown
    assert "Raw text" in reader.raw_markdown


def test_manual_url_add_creates_metadata_only_source_without_vault_writes(tmp_db):
    from app.services.studio_service import manual_add_url

    source, job = manual_add_url(
        tmp_db,
        url="https://example.com/manual",
        title="Manual Source",
        tags=["Local"],
    )

    processed_count = tmp_db.conn.execute(
        "SELECT COUNT(*) AS c FROM processed_sources"
    ).fetchone()["c"]
    vault_note_count = tmp_db.conn.execute(
        "SELECT COUNT(*) AS c FROM vault_notes"
    ).fetchone()["c"]

    assert job is None
    assert source.metadata_status == "metadata_only"
    assert source.content_status == "not_fetched"
    assert source.provider_refs[0].provider == "manual"
    assert source.tags[0].origin == "user"
    assert processed_count == 0
    assert vault_note_count == 0


def test_enqueue_action_creates_source_linked_processing_job(tmp_db):
    from app.services.studio_service import enqueue_source_action

    repo = SourceCatalogRepository(tmp_db)
    source = repo.upsert_source(CatalogSource(url="https://example.com/enqueue"))

    job = enqueue_source_action(
        tmp_db,
        source_uid=source.uid,
        action="capture",
        requested_reason="button click",
    )

    assert job.source_uid == source.uid
    assert job.task_type == "capture"
    assert job.mode == "safe"
    assert job.status == "queued"
    assert job.priority_reasons["explicit_request"] == 50


async def _noop():
    return None


def _settings(db_path: Path, vault_path: Path):
    settings = MagicMock()
    settings.db_path = db_path
    settings.vault_path = vault_path
    settings.automation_retry_max_attempts = 5
    settings.automation_retry_base_seconds = 60
    settings.configured_artifact_sink_ids = ["markdown_vault"]
    return settings


def test_one_shot_job_processor_updates_job_attempts_and_source_lifecycle(
    tmp_db,
    tmp_vault,
):
    import asyncio

    from app.models.source import SourceContent, SourceItem, SourceType
    from app.services.studio_service import enqueue_source_action, process_source_jobs_once

    repo = SourceCatalogRepository(tmp_db)
    source = repo.upsert_source(
        CatalogSource(
            url="https://example.com/job",
            title="Job Source",
            source_type="article",
        )
    )
    job = enqueue_source_action(tmp_db, source_uid=source.uid, action="capture")

    mock_content = SourceContent(
        source=SourceItem(
            url=source.url,
            title="Job Source",
            source_type=SourceType.ARTICLE,
        ),
        cleaned_text="Captured text for a Studio source job.",
        extraction_quality="full",
        url_hash=source.url_hash,
        content_hash="content123",
    )

    with (
        patch(
            "app.connectors.fetchers.fetch_content",
            new_callable=AsyncMock,
            return_value=mock_content,
        ),
        patch("app.sinks.registry.build_default_sink") as mock_build_sink,
    ):
        mock_sink = MagicMock()
        mock_sink.publish.return_value = [
            MagicMock(note_type="raw_capture", path="raw/articles/job.md"),
            MagicMock(note_type="source", path="wiki/sources/articles/job.md"),
        ]
        mock_build_sink.return_value = mock_sink

        jobs = asyncio.run(
            process_source_jobs_once(
                settings=_settings(tmp_db._path, tmp_vault),
                limit=1,
            )
        )

    refreshed_job = SourceCatalogRepository(tmp_db).get_processing_job(job.job_uid)
    refreshed_source = SourceCatalogRepository(tmp_db).get_source(source.uid)
    attempt_count = tmp_db.conn.execute(
        "SELECT COUNT(*) AS c FROM processing_attempts WHERE job_uid = ?",
        (job.job_uid,),
    ).fetchone()["c"]

    assert len(jobs) == 1
    assert refreshed_job is not None
    assert refreshed_job.status == "completed"
    assert refreshed_job.queued_item_id is not None
    assert refreshed_job.processed_source_id is not None
    assert attempt_count == 1
    assert refreshed_source is not None
    assert refreshed_source.metadata_status == "captured"
    assert refreshed_source.content_status == "available"
    assert refreshed_source.output_status == "published"


def test_snapshot_export_import_round_trips_metadata_refs_and_tags(tmp_path):
    source_db = Database(tmp_path / "source.db")
    source_db.connect()
    target_db = Database(tmp_path / "target.db")
    target_db.connect()
    try:
        source_repo = SourceCatalogRepository(source_db)
        source = source_repo.upsert_source(
            CatalogSource(
                url="https://example.com/snapshot",
                title="Snapshot Source",
                metadata_status="metadata_only",
                content_status="not_fetched",
            )
        )
        source_repo.attach_provider_ref(
            SourceProviderRef(
                source_uid=source.uid,
                provider="manual",
                external_url=source.url,
                title="Snapshot Source",
                metadata={"note": "local"},
            )
        )
        source_repo.sync_tags(source.uid, ["Keep"], origin="user")

        snapshot_path = tmp_path / "source_catalog.jsonl"
        snapshot = source_repo.export_snapshot(snapshot_path, reason="test")

        target_repo = SourceCatalogRepository(target_db)
        imported = target_repo.import_snapshot(Path(snapshot.snapshot_path))
        restored = target_repo.list_sources(query="snapshot")[0]

        assert imported == 1
        assert restored.metadata_status == "metadata_only"
        assert target_repo.provider_refs_for_source(restored.uid)[0].provider == "manual"
        assert target_repo.tags_for_source(restored.uid)[0].normalized_tag == "keep"
    finally:
        source_db.close()
        target_db.close()


def test_studio_api_lists_detail_and_enqueues(tmp_path, monkeypatch):
    from app.config import reset_settings
    from app.main import app

    db_path = tmp_path / "studio.db"
    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    db = Database(db_path)
    db.connect()
    repo = SourceCatalogRepository(db)
    source = repo.upsert_source(
        CatalogSource(
            url="https://example.com/api",
            title="API Source",
            saved_at=datetime(2026, 5, 4, tzinfo=timezone.utc),
        )
    )
    repo.attach_provider_ref(
        SourceProviderRef(
            source_uid=source.uid,
            provider="manual",
            external_url=source.url,
        )
    )
    repo.sync_tags(source.uid, ["API"], origin="user")
    db.close()

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("VAULT_PATH", str(vault_path))
    monkeypatch.delenv("EPISTORA_API_KEY", raising=False)
    reset_settings()
    try:
        with TestClient(app) as client:
            list_resp = client.get("/studio/sources", params={"q": "api"})
            assert list_resp.status_code == 200
            assert list_resp.json()["sources"][0]["uid"] == source.uid

            detail_resp = client.get(f"/studio/sources/{source.uid}")
            assert detail_resp.status_code == 200
            assert detail_resp.json()["provider_refs"][0]["provider"] == "manual"
            assert detail_resp.json()["tags"][0]["normalized_tag"] == "api"

            reader_resp = client.get(f"/studio/sources/{source.uid}/reader")
            assert reader_resp.status_code == 200
            assert reader_resp.json()["source_uid"] == source.uid

            enqueue_resp = client.post(
                f"/studio/sources/{source.uid}/actions/enqueue",
                json={"action": "capture", "requested_reason": "test"},
            )
            assert enqueue_resp.status_code == 200
            assert enqueue_resp.json()["source_uid"] == source.uid
            assert enqueue_resp.json()["task_type"] == "capture"

            jobs_resp = client.get("/studio/jobs")
            assert jobs_resp.status_code == 200
            assert jobs_resp.json()["jobs"][0]["source_uid"] == source.uid

            ui_resp = client.get("/studio")
            assert ui_resp.status_code == 200
            assert "Epistora Studio" in ui_resp.text
    finally:
        reset_settings()


def test_studio_source_list_filters_by_source_type_and_state(tmp_db):
    from app.services.studio_service import list_studio_sources

    repo = SourceCatalogRepository(tmp_db)
    repo.upsert_source(
        CatalogSource(
            url="https://example.com/article-only",
            title="Article",
            source_type="article",
            metadata_status="metadata_only",
            content_status="not_fetched",
        )
    )
    repo.upsert_source(
        CatalogSource(
            url="https://example.com/video-only",
            title="Video",
            source_type="youtube",
            metadata_status="metadata_only",
            content_status="not_fetched",
        )
    )
    captured = repo.upsert_source(
        CatalogSource(
            url="https://example.com/captured",
            title="Captured",
            source_type="article",
            metadata_status="captured",
            content_status="available",
        )
    )
    repo.update_lifecycle(captured.uid, brief_status="ready")

    articles = list_studio_sources(tmp_db, source_type="article")
    assert {s.title for s in articles} == {"Article", "Captured"}

    videos = list_studio_sources(tmp_db, source_type="youtube")
    assert [s.title for s in videos] == ["Video"]

    metadata_only = list_studio_sources(tmp_db, display_state="metadata_only")
    assert {s.title for s in metadata_only} == {"Article", "Video"}

    brief_ready = list_studio_sources(tmp_db, display_state="brief_ready")
    assert [s.title for s in brief_ready] == ["Captured"]


def test_studio_source_list_filters_by_provider_and_tag(tmp_db):
    from app.services.studio_service import list_studio_sources

    repo = SourceCatalogRepository(tmp_db)
    raindrop_source = repo.upsert_source(
        CatalogSource(url="https://example.com/raindrop", title="Raindrop Item")
    )
    repo.attach_provider_ref(
        SourceProviderRef(
            source_uid=raindrop_source.uid,
            provider="raindrop",
            external_id="rd-1",
            external_url=raindrop_source.url,
        )
    )
    repo.sync_tags(raindrop_source.uid, ["AI"], origin="provider")

    other = repo.upsert_source(
        CatalogSource(url="https://example.com/other", title="Other")
    )
    repo.attach_provider_ref(
        SourceProviderRef(
            source_uid=other.uid,
            provider="manual",
            external_url=other.url,
        )
    )

    raindrop_only = list_studio_sources(tmp_db, provider="raindrop")
    assert [s.title for s in raindrop_only] == ["Raindrop Item"]

    ai_tagged = list_studio_sources(tmp_db, tag="ai")
    assert [s.title for s in ai_tagged] == ["Raindrop Item"]


def test_jobs_list_includes_source_context_and_attempt_counts(tmp_db):
    from app.models.db import ProcessingAttempt
    from app.services.studio_service import list_studio_jobs

    repo = SourceCatalogRepository(tmp_db)
    source = repo.upsert_source(
        CatalogSource(
            url="https://example.com/queue",
            title="Queue Source",
            source_type="article",
        )
    )
    job = repo.enqueue_processing_job(
        source_uid=source.uid,
        task_type="capture",
        mode="safe",
        requested_by="studio",
    )
    repo.record_processing_attempt(
        ProcessingAttempt(
            job_uid=job.job_uid,
            attempt_number=1,
            success=False,
            error="boom",
        )
    )
    repo.record_processing_attempt(
        ProcessingAttempt(
            job_uid=job.job_uid,
            attempt_number=2,
            success=False,
            error="boom again",
        )
    )

    jobs = list_studio_jobs(tmp_db)
    assert len(jobs) == 1
    job_response = jobs[0]
    assert job_response.source_title == "Queue Source"
    assert job_response.source_url == source.url
    assert job_response.source_type == "article"
    assert job_response.attempt_count == 2


def test_reader_parses_frontmatter_and_returns_body(tmp_db, tmp_vault):
    from app.services.studio_service import get_studio_source_reader
    from app.utils.hashing import url_hash

    note_path = "wiki/sources/articles/with-frontmatter.md"
    raw_path = "raw/articles/with-frontmatter.md"
    (tmp_vault / "wiki" / "sources" / "articles").mkdir(parents=True, exist_ok=True)
    (tmp_vault / "raw" / "articles").mkdir(parents=True, exist_ok=True)
    (tmp_vault / note_path).write_text(
        "---\ntitle: Frontmatter Source\nsource_type: article\n---\n\n# Body\n\nReadable body.\n",
        encoding="utf-8",
    )
    (tmp_vault / raw_path).write_text("Raw text only", encoding="utf-8")

    source = SourceCatalogRepository(tmp_db).upsert_source(
        CatalogSource(
            url="https://example.com/with-frontmatter",
            title="Frontmatter Source",
            url_hash=url_hash("https://example.com/with-frontmatter"),
            metadata_status="captured",
            content_status="available",
        )
    )
    SourceRepository(tmp_db).upsert(
        ProcessedSource(
            url=source.url,
            url_hash=source.url_hash,
            title="Frontmatter Source",
            source_note_path=note_path,
            raw_capture_path=raw_path,
            status="completed",
        )
    )

    reader = get_studio_source_reader(tmp_db, source.uid, vault_path=tmp_vault)
    assert reader is not None
    assert reader.source_frontmatter.get("title") == "Frontmatter Source"
    assert "Body" in reader.source_body
    assert "title:" not in reader.source_body
    assert reader.raw_body == "Raw text only"


def test_studio_search_returns_source_and_note_provenance(tmp_db, tmp_vault):
    from app.services.studio_service import studio_search

    repo = SourceCatalogRepository(tmp_db)
    repo.upsert_source(
        CatalogSource(
            url="https://example.com/search-source",
            title="Searchable Article",
            description="A landmark article on machine learning",
            source_type="article",
        )
    )

    topic_dir = tmp_vault / "wiki" / "topics"
    topic_dir.mkdir(parents=True, exist_ok=True)
    (topic_dir / "machine-learning.md").write_text(
        "---\ntitle: Machine Learning\ntype: topic\n---\n\nMachine learning is a vast field.\n",
        encoding="utf-8",
    )

    response = studio_search(tmp_db, query="machine learning", vault_path=tmp_vault)
    kinds = {hit.kind for hit in response.hits}
    assert "source" in kinds
    titles = [hit.title for hit in response.hits]
    assert any("Searchable Article" in t for t in titles)


def test_knowledge_listing_returns_topics_from_vault(tmp_vault):
    from app.services.studio_service import list_knowledge_notes

    topic_dir = tmp_vault / "wiki" / "topics"
    topic_dir.mkdir(parents=True, exist_ok=True)
    (topic_dir / "physics.md").write_text(
        "---\ntitle: Physics\ntype: topic\n---\n\nFoundational science of motion and energy.\n",
        encoding="utf-8",
    )
    entity_dir = tmp_vault / "wiki" / "entities"
    entity_dir.mkdir(parents=True, exist_ok=True)
    (entity_dir / "feynman.md").write_text(
        "---\ntitle: Richard Feynman\ntype: entity\n---\n\nA physicist.\n",
        encoding="utf-8",
    )

    topics = list_knowledge_notes(note_type="topic", vault_path=tmp_vault)
    assert topics.note_type == "topic"
    assert any(note.title == "Physics" for note in topics.notes)

    entities = list_knowledge_notes(note_type="entity", vault_path=tmp_vault)
    assert any("Feynman" in note.title for note in entities.notes)


def test_studio_api_search_jobs_and_knowledge(tmp_path, monkeypatch):
    from app.config import reset_settings
    from app.main import app

    db_path = tmp_path / "studio.db"
    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    (vault_path / "wiki" / "topics").mkdir(parents=True, exist_ok=True)
    (vault_path / "wiki" / "topics" / "ai.md").write_text(
        "---\ntitle: AI\ntype: topic\n---\n\nArtificial intelligence overview.\n",
        encoding="utf-8",
    )

    db = Database(db_path)
    db.connect()
    repo = SourceCatalogRepository(db)
    source = repo.upsert_source(
        CatalogSource(
            url="https://example.com/ai-news",
            title="AI News",
            description="Latest AI breakthroughs",
            source_type="article",
        )
    )
    repo.enqueue_processing_job(
        source_uid=source.uid,
        task_type="capture",
        mode="safe",
        requested_by="studio",
    )
    db.close()

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("VAULT_PATH", str(vault_path))
    monkeypatch.delenv("EPISTORA_API_KEY", raising=False)
    reset_settings()
    try:
        with TestClient(app) as client:
            search_resp = client.get("/studio/search", params={"q": "ai"})
            assert search_resp.status_code == 200
            assert any(hit["kind"] == "source" for hit in search_resp.json()["hits"])

            jobs_resp = client.get("/studio/jobs")
            assert jobs_resp.status_code == 200
            jobs_payload = jobs_resp.json()["jobs"]
            assert jobs_payload[0]["source_title"] == "AI News"
            assert jobs_payload[0]["source_type"] == "article"
            assert "attempt_count" in jobs_payload[0]

            stats_resp = client.get("/studio/stats")
            assert stats_resp.status_code == 200
            stats_data = stats_resp.json()
            assert stats_data["total_sources"] >= 1
            assert "queue_jobs" in stats_data

            knowledge_resp = client.get("/studio/knowledge/topic")
            assert knowledge_resp.status_code == 200
            assert any(note["title"] == "AI" for note in knowledge_resp.json()["notes"])
    finally:
        reset_settings()


def test_studio_source_list_filters_by_type_via_api(tmp_path, monkeypatch):
    from app.config import reset_settings
    from app.main import app

    db_path = tmp_path / "studio.db"
    vault_path = tmp_path / "vault"
    vault_path.mkdir()

    db = Database(db_path)
    db.connect()
    repo = SourceCatalogRepository(db)
    repo.upsert_source(
        CatalogSource(
            url="https://example.com/article",
            title="Article",
            source_type="article",
        )
    )
    repo.upsert_source(
        CatalogSource(
            url="https://example.com/video",
            title="Video",
            source_type="youtube",
        )
    )
    db.close()

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("VAULT_PATH", str(vault_path))
    monkeypatch.delenv("EPISTORA_API_KEY", raising=False)
    reset_settings()
    try:
        with TestClient(app) as client:
            resp = client.get("/studio/sources", params={"source_type": "article"})
            assert resp.status_code == 200
            titles = [s["title"] for s in resp.json()["sources"]]
            assert titles == ["Article"]
    finally:
        reset_settings()


def test_studio_api_can_sync_readwise_with_bounded_auto_brief(tmp_path, monkeypatch):
    from app.config import reset_settings
    from app.main import app
    from app.services.brief_service import BriefCompilationResult, CompiledBriefSource
    from app.services.readwise_import_service import ReadwiseImportResult

    db_path = tmp_path / "studio.db"
    vault_path = tmp_path / "vault"
    vault_path.mkdir()

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("VAULT_PATH", str(vault_path))
    monkeypatch.delenv("EPISTORA_API_KEY", raising=False)
    reset_settings()
    try:
        with patch("app.api.routes_studio.sync_readwise_for_studio") as sync:
            sync.return_value = ReadwiseImportResult(
                imported=[
                    MagicMock(source_uid="src_1", raw_capture_path="raw/articles/one.md"),
                    MagicMock(source_uid="src_2", raw_capture_path="raw/articles/two.md"),
                ],
                failures=["https://example.com/bad: missing content"],
                auto_brief_result=BriefCompilationResult(
                    compiled=[
                        CompiledBriefSource(
                            source_uid="src_1",
                            source_note_path="wiki/sources/articles/one.md",
                            raw_capture_path="raw/articles/one.md",
                        )
                    ]
                ),
            )

            with TestClient(app) as client:
                resp = client.post(
                    "/studio/readwise/sync",
                    json={"limit": 25, "force": True, "auto_brief_limit": 1},
                )

        assert resp.status_code == 200
        assert resp.json() == {
            "imported_count": 2,
            "failed_count": 1,
            "auto_brief_compiled_count": 1,
            "auto_brief_failed_count": 0,
        }
        sync.assert_awaited_once_with(limit=25, force=True, auto_brief_limit=1)
    finally:
        reset_settings()


def test_studio_api_can_compile_pending_source_briefs(tmp_path, monkeypatch):
    from app.config import reset_settings
    from app.main import app
    from app.services.brief_service import BriefCompilationResult, CompiledBriefSource

    db_path = tmp_path / "studio.db"
    vault_path = tmp_path / "vault"
    vault_path.mkdir()

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("VAULT_PATH", str(vault_path))
    monkeypatch.delenv("EPISTORA_API_KEY", raising=False)
    reset_settings()
    try:
        with patch("app.api.routes_studio.compile_pending_briefs_for_studio") as compile_pending:
            compile_pending.return_value = BriefCompilationResult(
                compiled=[
                    CompiledBriefSource(
                        source_uid="src_1",
                        source_note_path="wiki/sources/articles/one.md",
                        raw_capture_path="raw/articles/one.md",
                    ),
                    CompiledBriefSource(
                        source_uid="src_2",
                        source_note_path="wiki/sources/articles/two.md",
                        raw_capture_path="raw/articles/two.md",
                    ),
                ],
                failures=["https://example.com/bad: backend failed"],
            )

            with TestClient(app) as client:
                resp = client.post(
                    "/studio/briefs/pending",
                    json={"limit": 10, "force": True},
                )

        assert resp.status_code == 200
        assert resp.json() == {"compiled_count": 2, "failed_count": 1}
        compile_pending.assert_awaited_once_with(limit=10, force=True)
    finally:
        reset_settings()


def test_studio_api_can_brief_one_source(tmp_path, monkeypatch):
    from app.config import reset_settings
    from app.main import app
    from app.services.brief_service import BriefCompilationResult, CompiledBriefSource

    db_path = tmp_path / "studio.db"
    vault_path = tmp_path / "vault"
    vault_path.mkdir()

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("VAULT_PATH", str(vault_path))
    monkeypatch.delenv("EPISTORA_API_KEY", raising=False)
    reset_settings()
    try:
        with patch("app.api.routes_studio.compile_source_brief_for_studio") as compile_source:
            compile_source.return_value = BriefCompilationResult(
                compiled=[
                    CompiledBriefSource(
                        source_uid="src_1",
                        source_note_path="wiki/sources/articles/one.md",
                        raw_capture_path="raw/articles/one.md",
                    )
                ]
            )

            with TestClient(app) as client:
                resp = client.post(
                    "/studio/sources/src_1/brief",
                    json={"force": True},
                )

        assert resp.status_code == 200
        assert resp.json() == {"compiled_count": 1, "failed_count": 0}
        compile_source.assert_awaited_once_with(source_uid="src_1", force=True)
    finally:
        reset_settings()
