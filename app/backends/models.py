"""Data models for the backend abstraction layer."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class TaskName(str, Enum):
    INGEST = "ingest"
    QUERY = "query"
    LINT = "lint"


class BackendType(str, Enum):
    API = "api"
    OPENCODE = "opencode"
    CLAUDE_CODE = "claude_code"


class BackendDescriptor(BaseModel):
    """Metadata about a configured backend."""

    backend_type: BackendType
    model: str = ""
    provider: str = ""
    available: bool = False
    reason: str = ""


class BackendRequest(BaseModel):
    """A request to a reasoning backend."""

    task: TaskName
    system_prompt: str = ""
    user_prompt: str = ""
    json_schema_hint: str = ""
    max_tokens: int = 4096
    temperature: float = 0.2


class BackendResponse(BaseModel):
    """The response from a reasoning backend."""

    text: str = ""
    backend_used: BackendType = BackendType.API
    model_used: str = ""
    was_fallback: bool = False
    fallback_reasons: list[str] = Field(default_factory=list)
    error: str = ""
    success: bool = True
