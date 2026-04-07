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

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    raindrop_api_token: str = ""
    raindrop_collection_id: int = 0

    vault_path: Path = Field(default=Path("./knowledge_vault"))
    database_url: str = "sqlite:///./data/app.db"

    log_level: str = "INFO"

    @property
    def db_path(self) -> Path:
        url = self.database_url
        if url.startswith("sqlite:///"):
            return Path(url.removeprefix("sqlite:///"))
        return Path("data/app.db")


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    global _settings
    _settings = None
