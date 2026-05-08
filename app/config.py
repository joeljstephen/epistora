"""Application settings with multi-backend and automation support."""

from __future__ import annotations

import os
import platform
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def project_root() -> Path:
    """Return the repository root when running from source."""
    return Path(__file__).resolve().parent.parent


def _default_epistora_home() -> Path:
    """Return the OS-appropriate home directory for Epistora config/state."""
    override = os.environ.get("EPISTORA_HOME")
    if override:
        return Path(override).expanduser()

    home = Path.home()
    system = platform.system()

    if system == "Windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "Epistora"
        return home / "AppData" / "Roaming" / "Epistora"

    if system == "Darwin":
        return home / "Library" / "Application Support" / "Epistora"

    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home).expanduser() / "epistora"

    return home / ".config" / "epistora"


def epistora_home() -> Path:
    """Public helper for the Epistora config/state directory."""
    return _default_epistora_home()


def epistora_logs_dir() -> Path:
    """Return the default log directory for scheduler helpers."""
    return epistora_home() / "logs"


def candidate_env_files(cwd: Path | None = None) -> tuple[Path, ...]:
    """Return env files in lookup priority order."""
    candidates: list[Path] = []

    explicit = os.environ.get("EPISTORA_ENV_FILE")
    if explicit:
        candidates.append(Path(explicit).expanduser())

    working_dir = (cwd or Path.cwd()).resolve()
    candidates.append(working_dir / ".env")

    root = project_root()
    inside_project_tree = root == working_dir or root in working_dir.parents

    if inside_project_tree:
        candidates.append(root / ".env")

    candidates.append(epistora_home() / ".env")

    if not inside_project_tree:
        candidates.append(root / ".env")

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.expanduser()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)

    return tuple(unique)


def existing_env_file(cwd: Path | None = None) -> Path | None:
    """Return the first existing env file in lookup order."""
    for path in candidate_env_files(cwd):
        if path.exists():
            return path
    return None


def preferred_env_file(cwd: Path | None = None) -> Path:
    """Return the env file path to create or update."""
    explicit = os.environ.get("EPISTORA_ENV_FILE")
    if explicit:
        return Path(explicit).expanduser()

    working_dir = (cwd or Path.cwd()).resolve()
    cwd_env = working_dir / ".env"
    if cwd_env.exists():
        return cwd_env

    root = project_root()
    inside_project_tree = root == working_dir or root in working_dir.parents
    if (working_dir / "pyproject.toml").exists() and (working_dir / "app").is_dir():
        return cwd_env

    if inside_project_tree:
        return root / ".env"

    return epistora_home() / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Legacy / global OpenAI (still used as API backend defaults) ---
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # --- Raindrop ---
    raindrop_api_token: str = ""
    raindrop_collection_id: int = 0

    # --- Readwise Reader ---
    readwise_api_token: str = ""

    # --- Vault / DB ---
    vault_path: Path = Field(default=Path("./knowledge_vault"))
    database_url: str = "sqlite:///./data/app.db"
    log_level: str = "INFO"
    epistora_api_key: str = ""
    artifact_sink_ids: str = "markdown_vault"
    json_export_dir: str = ".system/exports/json"
    evidence_blob_dir: str = ".system/blobs"
    evidence_blob_threshold_bytes: int = 50_000
    evidence_blob_preview_chars: int = 4_000

    # --- Backend fallback order (comma-separated: api,opencode,claude_code,codex) ---
    backend_order_ingest: str = "api,opencode,claude_code,codex"
    backend_order_query: str = "api,opencode,claude_code,codex"
    backend_order_lint: str = "api,opencode,claude_code,codex"
    backend_order_strict: bool = False

    # --- Direct API backend (global defaults) ---
    api_enabled: bool = True
    api_base_url: str = ""
    api_api_key: str = ""
    api_model: str = ""
    api_temperature: float = 0.2

    # --- API per-task overrides ---
    api_base_url_ingest: str = ""
    api_api_key_ingest: str = ""
    api_model_ingest: str = ""

    api_base_url_query: str = ""
    api_api_key_query: str = ""
    api_model_query: str = ""

    api_base_url_lint: str = ""
    api_api_key_lint: str = ""
    api_model_lint: str = ""

    # --- OpenCode CLI backend ---
    opencode_enabled: bool = True
    opencode_binary: str = "opencode"
    opencode_model: str = ""
    opencode_model_ingest: str = ""
    opencode_model_query: str = ""
    opencode_model_lint: str = ""
    opencode_timeout_seconds: int = 300

    # --- Claude Code CLI backend ---
    claude_code_enabled: bool = True
    claude_code_binary: str = "claude"
    claude_code_model: str = ""
    claude_code_model_ingest: str = ""
    claude_code_model_query: str = ""
    claude_code_model_lint: str = ""
    claude_code_timeout_seconds: int = 180

    # --- Codex CLI backend ---
    codex_enabled: bool = True
    codex_binary: str = "codex"
    codex_model: str = ""
    codex_model_ingest: str = ""
    codex_model_query: str = ""
    codex_model_lint: str = ""
    codex_timeout_seconds: int = 300

    # --- Extraction: Article ---
    article_fetch_timeout_seconds: int = 30
    article_use_readability_fallback: bool = True
    article_use_browser_fallback: bool = False

    # --- Extraction: YouTube ---
    youtube_fetch_timeout_seconds: int = 30
    youtube_use_ytdlp_fallback: bool = True
    youtube_transcript_max_chars: int = 0  # 0 = unlimited

    # --- Extraction: X/Twitter ---
    x_api_enabled: bool = False
    x_api_bearer_token: str = ""
    x_api_timeout_seconds: int = 30
    x_mirror_enabled: bool = True
    x_mirror_timeout_seconds: int = 20
    x_oembed_enabled: bool = True

    # --- Extraction: Browser fallback ---
    browser_fallback_enabled: bool = False
    browser_fallback_timeout_seconds: int = 30

    # --- Extraction: summarize.sh integration ---
    summarize_enabled: bool = False
    summarize_binary: str = "summarize"
    summarize_timeout_seconds: int = 180
    summarize_use_for_youtube_primary: bool = True
    summarize_use_for_article_fallback: bool = True
    summarize_use_for_generic_fallback: bool = True
    summarize_use_for_x_fallback: bool = True
    summarize_prefer_markdown: bool = True
    summarize_allow_daemon: bool = False
    summarize_daemon_url: str = ""
    summarize_weak_text_min_chars: int = 400
    summarize_weak_paragraph_min_count: int = 2
    summarize_weak_x_snippet_max_chars: int = 320

    # --- Ingest: LLM evidence window ---
    # Default cap for non-video sources (keeps prompts bounded).
    ingest_evidence_max_chars: int = 16000
    # YouTube transcripts are long; a larger window (or segment digests) is needed for
    # full-video analysis. 0 = same as ingest_evidence_max_chars.
    ingest_youtube_evidence_max_chars: int = 100_000
    # When the transcript exceeds ingest_youtube_evidence_max_chars, split into chunks of
    # roughly this size and digest each chunk before the final analysis pass.
    ingest_youtube_chunk_chars: int = 24_000

    # --- Automation / worker (legacy — still honoured by the interval-based worker) ---
    sync_enabled: bool = False
    sync_interval_seconds: int = 1200
    sync_batch_limit: int = 25

    auto_lint_enabled: bool = False
    auto_lint_interval_seconds: int = 86400

    auto_rebuild_indexes_enabled: bool = False
    auto_rebuild_indexes_interval_seconds: int = 21600

    # --- Queue-based automation ---
    automation_enabled: bool = False
    automation_default_mode: str = "safe"  # safe | balanced | deep

    automation_discover_batch_limit: int = 25
    automation_process_limit: int = 10
    automation_deep_enrich_limit_per_run: int = 3
    automation_deep_enrich_limit_per_day: int = 20

    automation_retry_max_attempts: int = 5
    automation_retry_base_seconds: int = 60

    automation_run_lint: bool = False
    automation_run_rebuild_indexes: bool = False

    automation_backend_order_safe: str = "api,opencode,claude_code,codex"
    automation_backend_order_balanced: str = "api,opencode,claude_code,codex"
    automation_backend_order_deep: str = "opencode,api,claude_code,codex"

    @property
    def db_path(self) -> Path:
        url = self.database_url
        if url.startswith("sqlite:///"):
            return Path(url.removeprefix("sqlite:///"))
        return Path("data/app.db")

    # --- Resolved helpers ---

    def effective_api_key(self) -> str:
        """Resolve API key: new setting → legacy OpenAI key."""
        return self.api_api_key or self.openai_api_key

    def effective_api_model(self) -> str:
        """Resolve model: new setting → legacy OpenAI model."""
        return self.api_model or self.openai_model

    @property
    def configured_artifact_sink_ids(self) -> list[str]:
        """Resolve configured sink ids, preserving order and removing duplicates."""
        sink_ids: list[str] = []
        for sink_id in self.artifact_sink_ids.split(","):
            normalized = sink_id.strip()
            if not normalized or normalized in sink_ids:
                continue
            sink_ids.append(normalized)
        return sink_ids or ["markdown_vault"]

_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings(_env_file=candidate_env_files())
    return _settings


def reset_settings() -> None:
    global _settings
    _settings = None
