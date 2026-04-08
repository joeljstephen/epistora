from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class ProcessedSource(BaseModel):
    id: int | None = None
    url: str
    url_hash: str
    content_hash: str = ""
    source_type: str = ""
    title: str = ""
    source_note_path: str = ""
    raw_capture_path: str = ""
    provider: str = ""
    external_id: str = ""
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    status: str = "completed"
    error_message: str = ""
    retry_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SyncCursor(BaseModel):
    connector: str
    last_sync_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cursor_value: str = ""


class VaultNoteMapping(BaseModel):
    note_path: str
    note_type: str  # source | topic | entity | concept | synthesis
    slug: str = ""
    title: str = ""
    source_url: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
