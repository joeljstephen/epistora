from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ChatRole = Literal["user", "assistant", "system", "tool"]
ChatBackendType = Literal["api", "opencode", "claude_code", "codex"]


class ChatMessageInput(BaseModel):
    role: ChatRole
    content: str = ""
    parts: list[dict[str, Any]] = Field(default_factory=list)


class SidebarChatRequest(BaseModel):
    source_id: str
    messages: list[ChatMessageInput] = Field(default_factory=list)


class BroadChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str = ""
    messages: list[ChatMessageInput] = Field(default_factory=list)
    source_context: dict[str, Any] | None = None


class ConversationCreateRequest(BaseModel):
    title: str = "New conversation"


class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: ChatRole
    content: str = ""
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime


class ChatSettingsRequest(BaseModel):
    backend_type: ChatBackendType = "api"
    api_key: str = ""
    base_url: str = ""
    model_name: str = ""


class ChatSettingsResponse(BaseModel):
    backend_type: ChatBackendType = "api"
    api_key: str = ""
    has_api_key: bool = False
    base_url: str = ""
    model_name: str = ""
    source: str = "default"
