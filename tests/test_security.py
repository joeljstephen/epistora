from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.storage.repositories import SourceRepository
from app.storage.sqlite import Database
from app.utils.http import UnsafeUrlError, assert_safe_http_url


def test_assert_safe_http_url_blocks_localhost():
    try:
        assert_safe_http_url("http://127.0.0.1:8000/private")
    except UnsafeUrlError as exc:
        assert "not allowed" in str(exc)
    else:
        raise AssertionError("expected UnsafeUrlError")


def test_assert_safe_http_url_rejects_file_scheme():
    try:
        assert_safe_http_url("file:///etc/passwd")
    except UnsafeUrlError as exc:
        assert "http://" in str(exc)
    else:
        raise AssertionError("expected UnsafeUrlError")


def test_ingest_route_requires_bearer_token(monkeypatch):
    monkeypatch.setenv("EPISTORA_API_KEY", "secret-token")
    from app.config import reset_settings

    reset_settings()
    with TestClient(app) as client:
        resp = client.get("/status")
        assert resp.status_code == 401

        ok = client.get(
            "/status",
            headers={"Authorization": "Bearer secret-token"},
        )
        assert ok.status_code == 200

    reset_settings()
    monkeypatch.delenv("EPISTORA_API_KEY", raising=False)
    reset_settings()


def test_ingest_url_route_returns_400_for_unsafe_target(monkeypatch):
    monkeypatch.delenv("EPISTORA_API_KEY", raising=False)
    from app.config import reset_settings

    reset_settings()
    with TestClient(app) as client:
        resp = client.post("/ingest/url", json={"url": "http://127.0.0.1/private"})
        assert resp.status_code == 400
        assert "not allowed" in resp.json()["detail"]


def test_database_migrates_legacy_raindrop_id(tmp_path: Path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE processed_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            url_hash TEXT NOT NULL UNIQUE,
            content_hash TEXT DEFAULT '',
            source_type TEXT DEFAULT '',
            title TEXT DEFAULT '',
            source_note_path TEXT DEFAULT '',
            raw_capture_path TEXT DEFAULT '',
            raindrop_id INTEGER,
            status TEXT DEFAULT 'completed',
            error_message TEXT DEFAULT '',
            retry_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO processed_sources (
            url, url_hash, content_hash, source_type, title, source_note_path, raw_capture_path,
            raindrop_id, status, error_message, retry_count, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "https://example.com/article",
            "url-hash",
            "content-hash",
            "article",
            "Example",
            "",
            "",
            12345,
            "completed",
            "",
            0,
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T00:00:00+00:00",
        ),
    )
    conn.commit()
    conn.close()

    db = Database(db_path)
    db.connect()
    source = SourceRepository(db).find_by_url_hash("url-hash")
    db.close()

    assert source is not None
    assert source.provider == "raindrop"
    assert source.external_id == "12345"
