from __future__ import annotations

from pathlib import Path

from app.models.source import SourceType

VAULT_DIRS = [
    "raw/articles",
    "raw/videos",
    "raw/threads",
    "raw/pdfs",
    "raw/misc",
    "raw/derived",
    "wiki/sources/articles",
    "wiki/sources/videos",
    "wiki/sources/threads",
    "wiki/sources/pdfs",
    "wiki/sources/misc",
    "wiki/sources/derived",
    "wiki/entities/people",
    "wiki/entities/companies",
    "wiki/entities/tools",
    "wiki/concepts",
    "wiki/topics",
    "wiki/synthesis",
    "wiki/indexes",
    "wiki/logs",
    "outputs/answers",
    "outputs/digests/daily",
    "outputs/digests/weekly",
    "outputs/digests/topic-bundles",
    "outputs/digests",
    "outputs/reports",
    ".system/manifests",
    ".system/cache",
    ".system/state",
    ".system/blobs",
    ".system/archives",
    ".obsidian/snippets",
]

RESETTABLE_DIRS = [
    "raw",
    "wiki/sources",
    "wiki/topics",
    "wiki/entities",
    "wiki/concepts",
    "wiki/synthesis",
    "wiki/indexes",
    "wiki/logs",
    "outputs/answers",
    "outputs/digests/daily",
    "outputs/digests/weekly",
    "outputs/digests/topic-bundles",
    "outputs/digests",
    "outputs/reports",
    ".system/cache",
    ".system/manifests",
    ".system/state",
    ".system/blobs",
]


RAW_DIRS: dict[SourceType, str] = {
    SourceType.ARTICLE: "raw/articles",
    SourceType.YOUTUBE: "raw/videos",
    SourceType.X_THREAD: "raw/threads",
    SourceType.PDF: "raw/pdfs",
    SourceType.GENERIC: "raw/misc",
    SourceType.DERIVED_WORK: "raw/derived",
}

SOURCE_NOTE_DIRS: dict[SourceType, str] = {
    SourceType.ARTICLE: "wiki/sources/articles",
    SourceType.YOUTUBE: "wiki/sources/videos",
    SourceType.X_THREAD: "wiki/sources/threads",
    SourceType.PDF: "wiki/sources/pdfs",
    SourceType.GENERIC: "wiki/sources/misc",
    SourceType.DERIVED_WORK: "wiki/sources/derived",
}


def vault_root(vault_path: Path) -> Path:
    return vault_path


def raw_capture_path(vault_path: Path, source_type: SourceType, slug: str) -> Path:
    return vault_path / RAW_DIRS[source_type] / f"{slug}.md"


def source_note_path(vault_path: Path, source_type: SourceType, slug: str) -> Path:
    return vault_path / SOURCE_NOTE_DIRS[source_type] / f"{slug}.md"


def topic_note_path(vault_path: Path, slug: str) -> Path:
    return vault_path / "wiki" / "topics" / f"{slug}.md"


def entity_note_path(vault_path: Path, slug: str) -> Path:
    return vault_path / "wiki" / "entities" / f"{slug}.md"


def entity_note_path_for_type(vault_path: Path, slug: str, entity_type: str) -> Path:
    directory_map = {
        "person": "people",
        "company": "companies",
        "tool": "tools",
    }
    subdir = directory_map.get(entity_type.lower())
    if subdir:
        return vault_path / "wiki" / "entities" / subdir / f"{slug}.md"
    return entity_note_path(vault_path, slug)


def concept_note_path(vault_path: Path, slug: str) -> Path:
    return vault_path / "wiki" / "concepts" / f"{slug}.md"


def synthesis_note_path(vault_path: Path, slug: str) -> Path:
    return vault_path / "wiki" / "synthesis" / f"{slug}.md"


def index_path(vault_path: Path) -> Path:
    return vault_path / "wiki" / "indexes" / "INDEX.md"


def topics_index_path(vault_path: Path) -> Path:
    return vault_path / "wiki" / "indexes" / "TOPICS.md"


def entities_index_path(vault_path: Path) -> Path:
    return vault_path / "wiki" / "indexes" / "ENTITIES.md"


def concepts_index_path(vault_path: Path) -> Path:
    return vault_path / "wiki" / "indexes" / "CONCEPTS.md"


def reading_home_path(vault_path: Path) -> Path:
    return vault_path / "wiki" / "indexes" / "READING_HOME.md"


def videos_index_path(vault_path: Path) -> Path:
    return vault_path / "wiki" / "indexes" / "VIDEOS.md"


def articles_index_path(vault_path: Path) -> Path:
    return vault_path / "wiki" / "indexes" / "ARTICLES.md"


def topics_feed_path(vault_path: Path) -> Path:
    return vault_path / "wiki" / "indexes" / "TOPICS_FEED.md"


def start_here_path(vault_path: Path) -> Path:
    return vault_path / "wiki" / "indexes" / "START_HERE.md"


def dashboard_path(vault_path: Path) -> Path:
    return vault_path / "DASHBOARD.md"


def query_protocol_path(vault_path: Path) -> Path:
    return vault_path / "wiki" / "indexes" / "QUERY_PROTOCOL.md"


def obsidian_reader_snippet_path(vault_path: Path) -> Path:
    return vault_path / ".obsidian" / "snippets" / "epistora-reader-views.css"


def topic_bundle_output_path(vault_path: Path, slug: str, timestamp: str) -> Path:
    return vault_path / "outputs" / "digests" / "topic-bundles" / f"{slug}--{timestamp}.md"


def daily_digest_output_path(vault_path: Path, period_key: str) -> Path:
    return vault_path / "outputs" / "digests" / "daily" / f"{period_key}.md"


def weekly_digest_output_path(vault_path: Path, period_key: str) -> Path:
    return vault_path / "outputs" / "digests" / "weekly" / f"{period_key}.md"


def ingest_log_path(vault_path: Path) -> Path:
    return vault_path / "wiki" / "logs" / "ingest-log.md"


def lint_log_path(vault_path: Path) -> Path:
    return vault_path / "wiki" / "logs" / "lint-log.md"


def maintenance_log_path(vault_path: Path) -> Path:
    return vault_path / "wiki" / "logs" / "maintenance-log.md"


def ensure_vault_dirs(vault_path: Path) -> None:
    for d in VAULT_DIRS:
        (vault_path / d).mkdir(parents=True, exist_ok=True)
