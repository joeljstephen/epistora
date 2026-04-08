from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("VAULT_PATH", "/tmp/epistora-test-vault")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_data/app.db")


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    """Create a temporary vault structure for testing."""
    from app.vault.paths import ensure_vault_dirs

    vault = tmp_path / "vault"
    vault.mkdir()
    ensure_vault_dirs(vault)
    return vault


@pytest.fixture
def tmp_db(tmp_path: Path):
    """Create a temporary database for testing."""
    from app.storage.sqlite import Database

    db_path = tmp_path / "test.db"
    db = Database(db_path)
    db.connect()
    yield db
    db.close()


@pytest.fixture
def sample_source_item():
    from app.models.source import SourceItem, SourceType

    return SourceItem(
        url="https://example.com/article/great-post",
        title="A Great Post About Testing",
        source_type=SourceType.ARTICLE,
        tags=["testing", "python"],
    )


@pytest.fixture
def sample_source_content(sample_source_item):
    from app.models.source import SourceContent

    return SourceContent(
        source=sample_source_item,
        raw_text="This is the raw HTML content of the article...",
        cleaned_text=(
            "This is a great post about testing in Python. It covers unit tests, "
            "integration tests, and more."
        ),
        author="Jane Doe",
        published_date="2025-01-15",
        word_count=18,
        extraction_quality="full",
        content_hash="abc123",
        url_hash="def456",
    )
