"""Application settings with multi-backend and automation support."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Legacy / global OpenAI (still used as API backend defaults) ---
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # --- Raindrop ---
    raindrop_api_token: str = ""
    raindrop_collection_id: int = 0

    # --- Vault / DB ---
    vault_path: Path = Field(default=Path("./knowledge_vault"))
    database_url: str = "sqlite:///./data/app.db"
    log_level: str = "INFO"
    epistora_api_key: str = ""

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

    # --- Ingest: LLM evidence window ---
    # Default cap for non-video sources (keeps prompts bounded).
    ingest_evidence_max_chars: int = 16000
    # YouTube transcripts are long; a larger window (or segment digests) is needed for
    # full-video analysis. 0 = same as ingest_evidence_max_chars.
    ingest_youtube_evidence_max_chars: int = 100_000
    # When the transcript exceeds ingest_youtube_evidence_max_chars, split into chunks of
    # roughly this size and digest each chunk before the final analysis pass.
    ingest_youtube_chunk_chars: int = 24_000

    # --- Automation / worker ---
    sync_enabled: bool = False
    sync_interval_seconds: int = 1200
    sync_batch_limit: int = 25

    auto_lint_enabled: bool = False
    auto_lint_interval_seconds: int = 86400

    auto_rebuild_indexes_enabled: bool = False
    auto_rebuild_indexes_interval_seconds: int = 21600

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

_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    global _settings
    _settings = None
