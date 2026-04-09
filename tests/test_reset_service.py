"""Tests for resetting generated vault artifacts."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.services.reset_service import reset_generated_state
from app.storage.sqlite import Database
from app.vault.paths import ensure_vault_dirs


def test_reset_generated_state_clears_generated_dirs_and_db(tmp_path: Path):
    vault = tmp_path / "vault"
    ensure_vault_dirs(vault)
    agents = vault / "AGENTS.md"
    agents.write_text("# Vault Rules\n", encoding="utf-8")

    raw_file = vault / "raw" / "articles" / "example.md"
    raw_file.write_text("# Raw Article\n", encoding="utf-8")
    source_file = vault / "wiki" / "sources" / "articles" / "example.md"
    source_file.write_text("# Source Note\n", encoding="utf-8")
    output_file = vault / "outputs" / "answers" / "answer.md"
    output_file.write_text("# Answer\n", encoding="utf-8")

    db_path = tmp_path / "app.db"
    db = Database(db_path)
    db.connect()
    db.conn.execute(
        "INSERT INTO processed_sources (url, url_hash, created_at, updated_at) VALUES (?, ?, ?, ?)",
        ("https://example.com", "hash1", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
    )
    db.conn.execute(
        (
            "INSERT INTO vault_notes "
            "(note_path, note_type, created_at, updated_at) VALUES (?, ?, ?, ?)"
        ),
        (
            "wiki/sources/articles/example.md",
            "source",
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T00:00:00+00:00",
        ),
    )
    db.conn.execute(
        "INSERT INTO sync_cursors (connector, last_sync_at, cursor_value) VALUES (?, ?, ?)",
        ("raindrop", "2026-01-01T00:00:00+00:00", ""),
    )
    db.conn.commit()
    db.close()

    with patch("app.services.reset_service.get_settings") as mock_settings:
        mock_settings.return_value.vault_path = vault
        mock_settings.return_value.db_path = db_path
        result = reset_generated_state(archive_existing=True)

    assert agents.exists()
    assert not raw_file.exists()
    assert not source_file.exists()
    assert not output_file.exists()
    assert (vault / "wiki" / "indexes" / "INDEX.md").exists()
    assert (vault / "wiki" / "logs" / "ingest-log.md").exists()

    archive_path = Path(str(result["archive_path"]))
    assert archive_path.exists()
    assert (archive_path / "raw" / "articles" / "example.md").exists()
    assert (archive_path / "wiki" / "sources" / "articles" / "example.md").exists()

    db = Database(db_path)
    db.connect()
    try:
        assert db.conn.execute("SELECT COUNT(*) FROM processed_sources").fetchone()[0] == 0
        assert db.conn.execute("SELECT COUNT(*) FROM vault_notes").fetchone()[0] == 0
        assert db.conn.execute("SELECT COUNT(*) FROM sync_cursors").fetchone()[0] == 0
    finally:
        db.close()
