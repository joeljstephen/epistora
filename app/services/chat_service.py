from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.backends.claude_code_cli import ClaudeCodeCliBackend
from app.backends.codex_cli import CodexCliBackend
from app.backends.models import BackendRequest, BackendType, TaskName
from app.backends.opencode_cli import OpenCodeCliBackend
from app.backends.registry import build_backends
from app.compiler.llm import run_text
from app.config import get_settings
from app.models.chat import (
    BroadChatRequest,
    ChatMessageInput,
    ChatSettingsRequest,
    ChatSettingsResponse,
    ConversationResponse,
    MessageResponse,
    SidebarChatRequest,
)
from app.models.db import UsageEvent
from app.models.studio import derive_display_state
from app.read_model.store import ReadModelStore
from app.retrieval.orchestrator import build_retrieval_context
from app.services.studio_service import (
    get_studio_source_reader,
    list_studio_sources,
)
from app.storage.repositories import SourceCatalogRepository
from app.storage.sqlite import Database
from app.utils.dates import iso_now

logger = logging.getLogger(__name__)

SIDEBAR_SYSTEM_PROMPT = """You are a knowledgeable assistant helping the user understand a specific
source in their personal knowledge base. You have access to the compiled
analysis and the raw extracted content for this source.

Answer questions about the source accurately. Reference specific sections
when possible. If the user asks about something not covered in this source,
say so and suggest they use the Broad Chat for vault-wide questions.

[COMPILED NOTE FOLLOWS]
{compiled_note}

[RAW CAPTURE FOLLOWS]
{raw_capture_truncated}
"""

BROAD_SYSTEM_PROMPT = """You are a knowledgeable assistant with full access to the user's personal
knowledge base (vault). You can search, read, and navigate their saved
sources, topics, entities, concepts, and the relationships between them.

Your role is to help the user understand, explore, and synthesize their
knowledge. You can:
- Answer questions about specific sources
- Find and list relevant sources on a topic
- Summarize across multiple sources
- Compare and contrast different sources
- Explain connections between topics, entities, and concepts
- Identify gaps or patterns in their knowledge

Always ground your answers in the user's actual saved content. Cite sources
by name when referencing them. Be thorough but concise.

When you use tools to search or read, explain what you're finding as you go.
"""

CLI_CHAT_OUTPUT_PROMPT = """You are running behind a chat UI. Return only the final
user-facing answer.
Do not include shell commands, command output, file listings, SQL, database schemas,
debug traces, raw table dumps, file paths as standalone evidence, or '(no output)'.
Use the context provided in the prompt. If the context is insufficient, say what is
missing briefly instead of probing the filesystem.
"""

CHAT_BACKEND_ORDER = ["api", "opencode", "claude_code", "codex"]
DEFAULT_CHAT_MODEL = "gpt-4o-mini"
RAW_CAPTURE_MAX_CHARS = 16_000
MAX_AGENT_STEPS = 6


class SearchSourcesArgs(BaseModel):
    query: str = Field(description="Keyword or phrase to search for.")
    source_type: str = Field(default="", description="Optional source type filter.")
    display_state: str = Field(default="", description="Optional lifecycle/display state filter.")
    tag: str = Field(default="", description="Optional normalized tag filter.")
    limit: int = Field(default=8, ge=1, le=25)


class ReadSourceArgs(BaseModel):
    source_id: str = Field(description="Studio source UID returned by source search/list tools.")


class ReadNoteArgs(BaseModel):
    path: str = Field(description="Vault-relative markdown path.")


class ListSourcesArgs(BaseModel):
    query: str = ""
    source_type: str = ""
    display_state: str = ""
    tag: str = ""
    limit: int = Field(default=12, ge=1, le=50)


class ListKnowledgeArgs(BaseModel):
    limit: int = Field(default=30, ge=1, le=100)


class SourceRelationsArgs(BaseModel):
    source_id: str = Field(description="Studio source UID.")


def list_conversations(db: Database) -> list[ConversationResponse]:
    rows = db.conn.execute(
        """
        SELECT id, title, created_at, updated_at, message_count
        FROM chat_conversations
        ORDER BY updated_at DESC
        """
    ).fetchall()
    return [ConversationResponse(**dict(row)) for row in rows]


def create_conversation(db: Database, title: str = "New conversation") -> ConversationResponse:
    conversation_id = f"chat_{uuid.uuid4().hex}"
    now = iso_now()
    db.conn.execute(
        """
        INSERT INTO chat_conversations (id, title, created_at, updated_at, message_count)
        VALUES (?, ?, ?, ?, 0)
        """,
        (conversation_id, _clean_title(title), now, now),
    )
    db.conn.commit()
    return get_conversation(db, conversation_id)  # type: ignore[return-value]


def get_conversation(db: Database, conversation_id: str) -> ConversationResponse | None:
    row = db.conn.execute(
        """
        SELECT id, title, created_at, updated_at, message_count
        FROM chat_conversations
        WHERE id = ?
        """,
        (conversation_id,),
    ).fetchone()
    return ConversationResponse(**dict(row)) if row else None


def delete_conversation(db: Database, conversation_id: str) -> None:
    db.conn.execute("DELETE FROM chat_messages WHERE conversation_id = ?", (conversation_id,))
    db.conn.execute("DELETE FROM chat_conversations WHERE id = ?", (conversation_id,))
    db.conn.commit()


def list_messages(db: Database, conversation_id: str) -> list[MessageResponse]:
    rows = db.conn.execute(
        """
        SELECT id, conversation_id, role, content, tool_calls, created_at
        FROM chat_messages
        WHERE conversation_id = ?
        ORDER BY created_at ASC, id ASC
        """,
        (conversation_id,),
    ).fetchall()
    messages: list[MessageResponse] = []
    for row in rows:
        payload = dict(row)
        payload["tool_calls"] = _json_list(payload.get("tool_calls"))
        messages.append(MessageResponse(**payload))
    return messages


def save_chat_settings(db: Database, request: ChatSettingsRequest) -> ChatSettingsResponse:
    current = _stored_settings(db)
    values = {
        "backend_type": request.backend_type,
        "base_url": request.base_url.strip(),
        "model_name": request.model_name.strip(),
    }
    if request.api_key:
        values["api_key"] = request.api_key.strip()
    elif current.get("api_key"):
        values["api_key"] = current["api_key"]

    now = iso_now()
    for key, value in values.items():
        db.conn.execute(
            """
            INSERT INTO chat_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value, now),
        )
    db.conn.commit()
    return get_chat_settings(db)


def get_chat_settings(db: Database) -> ChatSettingsResponse:
    resolved, source = _resolve_chat_settings(db)
    api_key = resolved.get("api_key", "")
    return ChatSettingsResponse(
        backend_type=resolved["backend_type"],  # type: ignore[arg-type]
        api_key=_mask_key(api_key),
        has_api_key=bool(api_key),
        base_url=resolved.get("base_url", ""),
        model_name=resolved.get("model_name", ""),
        source=source,
    )


async def sidebar_chat(db: Database, request: SidebarChatRequest) -> AsyncIterator[str]:
    settings = get_settings()
    vault_path = Path(settings.vault_path)
    reader = get_studio_source_reader(db, request.source_id, vault_path=vault_path)
    if reader is None:
        yield _sse_error("Source not found")
        yield _sse_done()
        return

    system_prompt = SIDEBAR_SYSTEM_PROMPT.format(
        compiled_note=reader.source_body or reader.source_markdown or "No compiled note available.",
        raw_capture_truncated=(
            _truncate_chars(reader.raw_body or reader.raw_markdown, RAW_CAPTURE_MAX_CHARS)
            or "No raw capture available."
        ),
    )
    messages = _to_langchain_messages(request.messages, system_prompt=system_prompt)
    if not any(isinstance(message, HumanMessage) for message in messages):
        yield _sse_error("At least one user message is required.")
        yield _sse_done()
        return

    async for chunk in _stream_llm_or_cli(
        db,
        messages=messages,
        system_prompt=system_prompt,
        fallback_prompt=_history_as_prompt(request.messages),
        task_type="chat_sidebar",
        metadata={"source_id": request.source_id},
    ):
        yield chunk


async def broad_chat(db: Database, request: BroadChatRequest) -> AsyncIterator[str]:
    user_text = (request.message or _last_user_text(request.messages)).strip()
    if not user_text:
        yield _sse_error("Message is required.")
        yield _sse_done()
        return

    conversation = _ensure_conversation(db, request.conversation_id, user_text)
    _insert_message(db, conversation.id, "user", user_text)

    persisted = list_messages(db, conversation.id)
    history = persisted[-20:]
    messages: list[Any] = [SystemMessage(content=BROAD_SYSTEM_PROMPT)]
    for message in history:
        if message.role == "user":
            messages.append(HumanMessage(content=message.content))
        elif message.role == "assistant":
            messages.append(AIMessage(content=message.content))

    if request.source_context:
        source_id = str(request.source_context.get("source_id") or "")
        title = str(request.source_context.get("title") or source_id)
        if source_id:
            messages.append(
                HumanMessage(
                    content=(
                        "The user opened Broad Chat from source "
                        f"{title} ({source_id}). Use read_source if this source matters."
                    )
                )
            )

    async for chunk in _stream_agent_or_cli(
        db,
        conversation_id=conversation.id,
        messages=messages,
        fallback_prompt=user_text,
    ):
        yield chunk


async def _stream_llm_or_cli(
    db: Database,
    *,
    messages: list[Any],
    system_prompt: str,
    fallback_prompt: str,
    task_type: str,
    metadata: dict[str, Any],
) -> AsyncIterator[str]:
    resolved, _ = _resolve_chat_settings(db)
    backend_type = resolved["backend_type"]
    message_id = f"msg_{uuid.uuid4().hex}"
    text_id = f"text_{uuid.uuid4().hex}"
    yield _sse({"type": "start", "messageId": message_id})
    yield _sse({"type": "text-start", "id": text_id})

    final_text = ""
    backend_used = backend_type
    model_used = resolved.get("model_name", "")

    if (
        backend_type == BackendType.API.value
        and resolved.get("api_key")
        and resolved.get("model_name")
    ):
        try:
            llm = _chat_llm(resolved)
            async for chunk in llm.astream(messages):
                text = _chunk_text(chunk.content)
                if text:
                    final_text += text
                    yield _sse({"type": "text-delta", "id": text_id, "delta": text})
        except Exception as exc:
            logger.exception("Streaming API chat failed")
            yield _sse({"type": "error", "errorText": str(exc)})
    else:
        resp = await _run_cli_or_router(
            db,
            system_prompt=system_prompt,
            user_prompt=fallback_prompt,
        )
        final_text = _clean_cli_response(resp.text if resp.success else resp.error)
        backend_used = resp.backend_used
        model_used = resp.model_used
        yield _sse(
            {
                "type": "data-chat-meta",
                "data": {
                    "nonStreaming": True,
                    "backend": backend_used,
                    "model": model_used,
                },
            }
        )
        yield _sse({"type": "text-delta", "id": text_id, "delta": final_text})

    yield _sse({"type": "text-end", "id": text_id})
    yield _sse(
        {"type": "data-chat-meta", "data": _usage_payload(final_text, backend_used, model_used)}
    )
    yield _sse({"type": "finish"})
    yield _sse_done()
    _record_usage(
        db,
        task_type=task_type,
        text=final_text,
        backend=backend_used,
        model=model_used,
        metadata=metadata,
    )


async def _stream_agent_or_cli(
    db: Database,
    *,
    conversation_id: str,
    messages: list[Any],
    fallback_prompt: str,
) -> AsyncIterator[str]:
    resolved, _ = _resolve_chat_settings(db)
    backend_type = resolved["backend_type"]
    message_id = f"msg_{uuid.uuid4().hex}"
    text_id = f"text_{uuid.uuid4().hex}"
    tool_calls: list[dict[str, Any]] = []
    final_text = ""
    backend_used = backend_type
    model_used = resolved.get("model_name", "")

    yield _sse({"type": "start", "messageId": message_id})

    if (
        backend_type == BackendType.API.value
        and resolved.get("api_key")
        and resolved.get("model_name")
    ):
        try:
            llm = _chat_llm(resolved).bind_tools(_agent_tools(db))
            for step in range(MAX_AGENT_STEPS):
                yield _sse({"type": "start-step"})
                response = None
                streamed_step_text = ""
                text_started = False
                async for chunk in llm.astream(messages):
                    response = chunk if response is None else response + chunk
                    text = _chunk_text(chunk.content)
                    if text:
                        if not text_started:
                            yield _sse({"type": "text-start", "id": text_id})
                            text_started = True
                        streamed_step_text += text
                        yield _sse({"type": "text-delta", "id": text_id, "delta": text})
                if response is None:
                    response = await llm.ainvoke(messages)
                if text_started:
                    yield _sse({"type": "text-end", "id": text_id})
                messages.append(response)
                calls = list(getattr(response, "tool_calls", []) or [])
                if not calls:
                    final_text += streamed_step_text or _message_text(response.content)
                    if not text_started and final_text:
                        yield _sse({"type": "text-start", "id": text_id})
                        yield _sse({"type": "text-delta", "id": text_id, "delta": final_text})
                        yield _sse({"type": "text-end", "id": text_id})
                    yield _sse({"type": "finish-step"})
                    break
                final_text += streamed_step_text

                for call in calls:
                    tool_name = str(call.get("name", ""))
                    tool_args = dict(call.get("args") or {})
                    tool_call_id = str(call.get("id") or f"call_{uuid.uuid4().hex}")
                    status = _tool_status(tool_name, tool_args)
                    tool_calls.append({"name": tool_name, "args": tool_args, "id": tool_call_id})
                    yield _sse(
                        {
                            "type": "data-tool-status",
                            "data": {"status": status, "tool": tool_name},
                        }
                    )
                    yield _sse(
                        {
                            "type": "tool-input-available",
                            "toolCallId": tool_call_id,
                            "toolName": tool_name,
                            "input": tool_args,
                        }
                    )
                    output = _execute_tool(db, tool_name, tool_args)
                    yield _sse(
                        {
                            "type": "tool-output-available",
                            "toolCallId": tool_call_id,
                            "output": _compact_tool_output(output),
                        }
                    )
                    messages.append(
                        ToolMessage(
                            content=json.dumps(output),
                            tool_call_id=tool_call_id,
                        )
                    )
                yield _sse({"type": "finish-step"})
            else:
                final_text = "I reached the tool step limit before completing the answer."
                yield _sse({"type": "text-start", "id": text_id})
                yield _sse({"type": "text-delta", "id": text_id, "delta": final_text})
                yield _sse({"type": "text-end", "id": text_id})
        except Exception as exc:
            logger.exception("Broad chat agent failed")
            final_text = f"Broad chat failed: {exc}"
            yield _sse({"type": "error", "errorText": str(exc)})
    else:
        context = _broad_cli_context(db, fallback_prompt)
        system_prompt = (
            f"{BROAD_SYSTEM_PROMPT}\n\n{CLI_CHAT_OUTPUT_PROMPT}\n\n"
            f"Read-only context available to answer the user:\n{context}"
        )
        resp = await _run_cli_or_router(
            db,
            system_prompt=system_prompt,
            user_prompt=(
                f"{fallback_prompt}\n\n"
                "Answer from the read-only context above. Return only the final answer."
            ),
        )
        final_text = _clean_cli_response(resp.text if resp.success else resp.error)
        backend_used = resp.backend_used
        model_used = resp.model_used
        yield _sse(
            {
                "type": "data-chat-meta",
                "data": {"nonStreaming": True, "backend": backend_used, "model": model_used},
            }
        )
        yield _sse({"type": "text-start", "id": text_id})
        yield _sse({"type": "text-delta", "id": text_id, "delta": final_text})
        yield _sse({"type": "text-end", "id": text_id})

    _insert_message(db, conversation_id, "assistant", final_text, tool_calls=tool_calls)
    yield _sse(
        {"type": "data-chat-meta", "data": _usage_payload(final_text, backend_used, model_used)}
    )
    yield _sse({"type": "data-conversation", "data": {"conversationId": conversation_id}})
    yield _sse({"type": "finish"})
    yield _sse_done()
    _record_usage(
        db,
        task_type="chat_broad",
        text=final_text,
        backend=backend_used,
        model=model_used,
        metadata={"conversation_id": conversation_id, "tool_calls": tool_calls},
    )


def _agent_tools(db: Database) -> list[StructuredTool]:
    return [
        StructuredTool.from_function(
            name="search_sources",
            description="Find sources by keyword, type, lifecycle state, or tag.",
            args_schema=SearchSourcesArgs,
            func=lambda **kwargs: _tool_search_sources(db, **kwargs),
        ),
        StructuredTool.from_function(
            name="read_source",
            description="Read a source's metadata, compiled note, and raw capture.",
            args_schema=ReadSourceArgs,
            func=lambda **kwargs: _tool_read_source(db, **kwargs),
        ),
        StructuredTool.from_function(
            name="read_note",
            description="Read any vault markdown file by vault-relative path.",
            args_schema=ReadNoteArgs,
            func=lambda **kwargs: _tool_read_note(**kwargs),
        ),
        StructuredTool.from_function(
            name="list_sources",
            description="List or filter catalog sources.",
            args_schema=ListSourcesArgs,
            func=lambda **kwargs: _tool_list_sources(db, **kwargs),
        ),
        StructuredTool.from_function(
            name="list_knowledge",
            description="Browse topics, entities, and concepts in the read model.",
            args_schema=ListKnowledgeArgs,
            func=lambda **kwargs: _tool_list_knowledge(**kwargs),
        ),
        StructuredTool.from_function(
            name="get_source_relations",
            description="Find read-model relations connected to a source.",
            args_schema=SourceRelationsArgs,
            func=lambda **kwargs: _tool_source_relations(db, **kwargs),
        ),
    ]


def _execute_tool(db: Database, tool_name: str, tool_args: dict[str, Any]) -> dict[str, Any]:
    tools: dict[str, Callable[..., dict[str, Any]]] = {
        "search_sources": lambda **kwargs: _tool_search_sources(db, **kwargs),
        "read_source": lambda **kwargs: _tool_read_source(db, **kwargs),
        "read_note": _tool_read_note,
        "list_sources": lambda **kwargs: _tool_list_sources(db, **kwargs),
        "list_knowledge": _tool_list_knowledge,
        "get_source_relations": lambda **kwargs: _tool_source_relations(db, **kwargs),
    }
    tool = tools.get(tool_name)
    if tool is None:
        return {"error": f"Unknown tool: {tool_name}"}
    try:
        return tool(**tool_args)
    except Exception as exc:
        logger.exception("Chat tool failed: %s", tool_name)
        return {"error": str(exc)}


def _tool_search_sources(
    db: Database,
    query: str,
    source_type: str = "",
    display_state: str = "",
    tag: str = "",
    limit: int = 8,
) -> dict[str, Any]:
    repo = SourceCatalogRepository(db)
    catalog_sources = repo.list_sources(
        limit=limit,
        query=query,
        source_type=source_type,
        display_state=display_state,
        tag=tag,
    )
    vault_path = Path(get_settings().vault_path)
    retrieval = build_retrieval_context(vault_path, query, limit=limit)
    sources = [_source_payload(source) for source in catalog_sources]
    notes = [
        {
            "note_path": artifact.note.note_path,
            "title": artifact.note.title,
            "note_type": artifact.note.note_type,
            "score": artifact.score,
            "snippet": artifact.snippet,
        }
        for artifact in retrieval.artifacts
    ]
    return {"query": query, "sources": sources, "notes": notes}


def _tool_read_source(db: Database, source_id: str) -> dict[str, Any]:
    repo = SourceCatalogRepository(db)
    source = repo.get_source(source_id)
    if source is None:
        return {"error": "Source not found", "source_id": source_id}
    reader = get_studio_source_reader(db, source_id, vault_path=Path(get_settings().vault_path))
    return {
        **_source_payload(source),
        "source_note_path": reader.source_note_path if reader else "",
        "raw_capture_path": reader.raw_capture_path if reader else "",
        "compiled_note": _truncate_chars(reader.source_body if reader else "", 24_000),
        "raw_capture": _truncate_chars(reader.raw_body if reader else "", RAW_CAPTURE_MAX_CHARS),
    }


def _tool_read_note(path: str) -> dict[str, Any]:
    vault_path = Path(get_settings().vault_path)
    candidate = _resolve_vault_path(vault_path, path)
    if candidate is None or not candidate.is_file():
        return {"error": "Note not found", "path": path}
    return {
        "path": path,
        "content": _truncate_chars(candidate.read_text(encoding="utf-8"), 32_000),
    }


def _tool_list_sources(
    db: Database,
    query: str = "",
    source_type: str = "",
    display_state: str = "",
    tag: str = "",
    limit: int = 12,
) -> dict[str, Any]:
    sources = list_studio_sources(
        db,
        query=query,
        limit=limit,
        source_type=source_type,
        display_state=display_state,
        tag=tag,
    )
    return {"sources": [source.model_dump(mode="json") for source in sources]}


def _tool_list_knowledge(limit: int = 30) -> dict[str, Any]:
    store = ReadModelStore(Path(get_settings().vault_path))
    store.ensure_populated()
    return {
        f"{note_type}s": [
            {
                "note_path": note.note_path,
                "title": note.title,
                "tags": note.tags,
                "source_url": note.source_url,
            }
            for note in store.list_notes(note_type=note_type, limit=limit)
        ]
        for note_type in ("topic", "entity", "concept")
    }


def _tool_source_relations(db: Database, source_id: str) -> dict[str, Any]:
    source = SourceCatalogRepository(db).get_source(source_id)
    if source is None:
        return {"error": "Source not found", "source_id": source_id}
    reader = get_studio_source_reader(db, source_id, vault_path=Path(get_settings().vault_path))
    note_path = reader.source_note_path if reader else ""
    if not note_path:
        return {"source": _source_payload(source), "relations": []}
    store = ReadModelStore(Path(get_settings().vault_path))
    store.ensure_populated()
    edges = store.get_edges(from_note_path=note_path) + store.get_edges(to_note_path=note_path)
    return {
        "source": _source_payload(source),
        "note_path": note_path,
        "relations": [edge.model_dump(mode="json") for edge in edges[:50]],
    }


def _source_payload(source: Any) -> dict[str, Any]:
    return {
        "uid": source.uid,
        "title": source.title or source.url,
        "url": source.url,
        "source_type": source.source_type,
        "display_state": derive_display_state(source),
        "tags": source.tag_snapshot,
        "saved_at": source.saved_at.isoformat() if source.saved_at else None,
    }


def _ensure_conversation(
    db: Database,
    conversation_id: str | None,
    first_message: str,
) -> ConversationResponse:
    if conversation_id:
        existing = get_conversation(db, conversation_id)
        if existing:
            return existing
    return create_conversation(db, _title_from_message(first_message))


def _insert_message(
    db: Database,
    conversation_id: str,
    role: str,
    content: str,
    *,
    tool_calls: list[dict[str, Any]] | None = None,
) -> None:
    now = iso_now()
    db.conn.execute(
        """
        INSERT INTO chat_messages (id, conversation_id, role, content, tool_calls, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            f"cmsg_{uuid.uuid4().hex}",
            conversation_id,
            role,
            content,
            json.dumps(tool_calls or [], sort_keys=True),
            now,
        ),
    )
    row = db.conn.execute(
        "SELECT COUNT(*) AS count FROM chat_messages WHERE conversation_id = ?",
        (conversation_id,),
    ).fetchone()
    db.conn.execute(
        """
        UPDATE chat_conversations
        SET updated_at = ?, message_count = ?
        WHERE id = ?
        """,
        (now, int(row["count"] if row else 0), conversation_id),
    )
    db.conn.commit()


def _resolve_chat_settings(db: Database) -> tuple[dict[str, str], str]:
    settings = get_settings()
    stored = _stored_settings(db)
    default_backend = _first_backend(settings.backend_order_query) or BackendType.API.value
    env_values = {
        "backend_type": default_backend,
        "api_key": settings.effective_api_key(),
        "base_url": settings.api_base_url,
        "model_name": settings.effective_api_model() or DEFAULT_CHAT_MODEL,
    }
    resolved = {**env_values, **{key: value for key, value in stored.items() if value}}
    return resolved, "app" if stored else "env" if env_values["api_key"] else "default"


def _stored_settings(db: Database) -> dict[str, str]:
    rows = db.conn.execute("SELECT key, value FROM chat_settings").fetchall()
    return {str(row["key"]): str(row["value"]) for row in rows}


def _chat_llm(resolved: dict[str, str]) -> ChatOpenAI:
    kwargs: dict[str, Any] = {
        "model": resolved["model_name"],
        "api_key": resolved["api_key"],
        "temperature": 0.2,
        "streaming": True,
    }
    if resolved.get("base_url"):
        kwargs["base_url"] = resolved["base_url"]
    return ChatOpenAI(**kwargs)


async def _run_cli_or_router(db: Database, *, system_prompt: str, user_prompt: str):
    resolved, _ = _resolve_chat_settings(db)
    preferred = resolved["backend_type"]
    if preferred != BackendType.API.value:
        settings = get_settings()
        backends = build_backends(settings)
        preferred_backend = _chat_cli_backend(preferred, resolved)
        if preferred_backend is not None:
            backends[preferred] = preferred_backend
        request = BackendRequest(
            task=TaskName.QUERY,
            system_prompt=f"{system_prompt}\n\n{CLI_CHAT_OUTPUT_PROMPT}",
            user_prompt=user_prompt,
        )
        ordered = [preferred, *[backend for backend in CHAT_BACKEND_ORDER if backend != preferred]]
        reasons: list[str] = []
        for backend_id in ordered:
            if backend_id == BackendType.API.value:
                continue
            backend = backends.get(backend_id)
            if backend is None:
                reasons.append(f"{backend_id}: not registered")
                continue
            if not backend.is_available(TaskName.QUERY):
                desc = backend.describe(TaskName.QUERY)
                reasons.append(f"{backend_id}: {desc.reason or 'unavailable'}")
                continue
            response = await backend.generate(request)
            if response.success:
                response.was_fallback = backend_id != preferred or bool(reasons)
                response.fallback_reasons = reasons
                return response
            reasons.append(f"{backend_id}: {response.error}")
    return await run_text(TaskName.QUERY, system_prompt=system_prompt, user_prompt=user_prompt)


def _chat_cli_backend(backend_type: str, resolved: dict[str, str]):
    settings = get_settings()
    model = resolved.get("model_name", "")
    if backend_type == BackendType.OPENCODE.value:
        configured_model = settings.opencode_model_query or settings.opencode_model
        return OpenCodeCliBackend(
            enabled=settings.opencode_enabled,
            binary=settings.opencode_binary,
            model=_with_provider_prefix(model, configured_model) or configured_model,
            timeout_seconds=settings.opencode_timeout_seconds,
        )
    if backend_type == BackendType.CLAUDE_CODE.value:
        return ClaudeCodeCliBackend(
            enabled=settings.claude_code_enabled,
            binary=settings.claude_code_binary,
            model=model or settings.claude_code_model,
            timeout_seconds=settings.claude_code_timeout_seconds,
        )
    if backend_type == BackendType.CODEX.value:
        return CodexCliBackend(
            enabled=settings.codex_enabled,
            binary=settings.codex_binary,
            model=model or settings.codex_model,
            timeout_seconds=settings.codex_timeout_seconds,
        )
    return None


def _with_provider_prefix(model: str, configured_model: str) -> str:
    if not model or "/" in model or "/" not in configured_model:
        return model
    provider, _ = configured_model.split("/", 1)
    return f"{provider}/{model}"


def _to_langchain_messages(messages: list[ChatMessageInput], *, system_prompt: str) -> list[Any]:
    result: list[Any] = [SystemMessage(content=system_prompt)]
    for message in messages[-16:]:
        text = _message_input_text(message).strip()
        if not text:
            continue
        if message.role == "assistant":
            result.append(AIMessage(content=text))
        elif message.role == "user":
            result.append(HumanMessage(content=text))
    return result


def _history_as_prompt(messages: list[ChatMessageInput]) -> str:
    return "\n".join(
        f"{message.role}: {_message_input_text(message)}"
        for message in messages[-16:]
        if _message_input_text(message).strip()
    )


def _last_user_text(messages: list[ChatMessageInput]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return _message_input_text(message)
    return ""


def _message_input_text(message: ChatMessageInput) -> str:
    if message.content:
        return message.content
    texts: list[str] = []
    for part in message.parts:
        if part.get("type") == "text" and part.get("text"):
            texts.append(str(part["text"]))
    return "\n".join(texts)


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for part in content:
            if isinstance(part, dict) and part.get("text"):
                texts.append(str(part["text"]))
            else:
                texts.append(str(part))
        return "\n".join(texts)
    return str(content or "")


def _broad_cli_context(db: Database, query: str) -> str:
    settings = get_settings()
    vault_path = Path(settings.vault_path)
    sections = [_recent_sources_context(db)]
    try:
        retrieval = build_retrieval_context(vault_path, query, limit=8)
        if retrieval.text_context.strip():
            sections.append("Relevant vault excerpts:\n" + retrieval.text_context.strip())
    except Exception:
        logger.info("Failed to build broad chat retrieval context", exc_info=True)
    return "\n\n".join(section for section in sections if section.strip())


def _recent_sources_context(db: Database, limit: int = 10) -> str:
    rows = db.conn.execute(
        """
        SELECT uid, title, url, source_type, site_name, saved_at, created_at, description,
               content_status, brief_status, deep_status
        FROM sources
        ORDER BY COALESCE(saved_at, created_at) DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    if not rows:
        return "Recent saved sources: none."

    lines = ["Recent saved sources, newest first:"]
    for row in rows:
        title = str(row["title"] or row["url"] or "Untitled")
        source_type = str(row["source_type"] or "source")
        saved_at = str(row["saved_at"] or row["created_at"] or "")
        site = str(row["site_name"] or "")
        url = str(row["url"] or "")
        status = ", ".join(
            value
            for value in (
                str(row["content_status"] or ""),
                str(row["brief_status"] or ""),
                str(row["deep_status"] or ""),
            )
            if value
        )
        description = _truncate_chars(str(row["description"] or ""), 240)
        line = f"- {title} ({source_type}, saved {saved_at})"
        if site:
            line += f" from {site}"
        if status:
            line += f" [{status}]"
        line += f"\n  URL: {url}"
        if description:
            line += f"\n  Description: {description}"
        lines.append(line)
    return "\n".join(lines)


def _clean_cli_response(text: str) -> str:
    """Remove CLI agent trace noise before sending chat output to the UI."""
    original = _strip_ansi(text or "")
    lines = original.splitlines()
    cleaned: list[str] = []
    dropping_command_output = False
    dropping_noise_block = False
    dropped_noise = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            dropping_command_output = False
            dropping_noise_block = False
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue
        if _looks_like_cli_trace(stripped):
            dropping_command_output = stripped.startswith("$")
            dropped_noise = True
            continue
        if dropping_command_output and _looks_like_command_output(stripped):
            dropped_noise = True
            continue
        if dropping_noise_block:
            if _looks_like_answer_start(stripped):
                dropping_noise_block = False
            else:
                dropped_noise = True
                continue
        if _looks_like_cli_noise(stripped):
            dropping_noise_block = _starts_noise_block(stripped)
            dropped_noise = True
            continue
        dropping_command_output = False
        cleaned.append(line)

    result = "\n".join(cleaned).strip()
    result = _crop_to_answer(result, dropped_noise).strip()
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result or "I couldn't produce a clean answer from the selected backend."


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)


def _looks_like_cli_trace(line: str) -> bool:
    return (
        line.startswith("✱ ")
        or line.startswith("✗ ")
        or line.startswith("$ ")
        or line.startswith("⎿ ")
        or line.startswith("→ ")
    )


def _looks_like_command_output(line: str) -> bool:
    return _looks_like_shell_listing(line) or _looks_like_cli_noise(line)


def _looks_like_shell_listing(line: str) -> bool:
    return (
        line.startswith("total ")
        or line.startswith("drwx")
        or line.startswith("-rw")
        or line.startswith("lrwx")
    )


def _looks_like_cli_noise(line: str) -> bool:
    lower = line.lower()
    if line == "(no output)":
        return True
    if line.startswith(("ls: ", "Error: in prepare", "CREATE TABLE ", "CREATE INDEX ")):
        return True
    if line.startswith(("SELECT ", "FROM ", "WHERE ", "ORDER BY ")):
        return True
    if "no knowledge_vault dir" in lower:
        return True
    if "knowledge_vault/" in line or ".system/epistora.db" in line:
        return True
    if "haven't been written to disk" in lower:
        return True
    if "no such file or directory" in lower:
        return True
    if "sqlite_sequence" in line or "processed_sources" in line and "vault_notes" in line:
        return True
    if re.fullmatch(r"[\w./-]*app\.db(?:\s+[\w./-]*\.db)+", line):
        return True
    if _looks_like_raw_pipe_dump(line):
        return True
    return False


def _starts_noise_block(line: str) -> bool:
    return line.startswith(("Error: in prepare", "CREATE TABLE ", "CREATE INDEX ", "SELECT "))


def _looks_like_answer_start(line: str) -> bool:
    return any(
        re.search(pattern, line, re.IGNORECASE)
        for pattern in (
            r"^your most recent save is:?",
            r"^the most recent save is:?",
            r"^most recent save:?",
            r"^based on\b",
            r"^here(?:'s| is| are)\b",
            r"^i found\b",
            r"^summary\b",
            r"^in short\b",
            r"^overall\b",
        )
    )


def _looks_like_raw_pipe_dump(line: str) -> bool:
    if line.startswith("|"):
        return False
    pipe_count = line.count("|")
    if pipe_count < 3:
        return False
    if "http://" in line or "https://" in line or "wiki/" in line or "inbox/" in line:
        return True
    if re.match(r"^\d+\|", line):
        return True
    return False


def _crop_to_answer(text: str, had_noise: bool) -> str:
    if not had_noise:
        return text
    lines = text.splitlines()
    answer_markers = [
        re.compile(pattern, re.IGNORECASE)
        for pattern in (
            r"^your most recent save is:?",
            r"^the most recent save is:?",
            r"^most recent save:?",
            r"^based on\b",
            r"^here(?:'s| is| are)\b",
            r"^i found\b",
            r"^summary\b",
            r"^in short\b",
            r"^overall\b",
        )
    ]
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if any(marker.search(stripped) for marker in answer_markers):
            return "\n".join(lines[idx:])
    return text


def _chunk_text(content: Any) -> str:
    return _message_text(content)


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _sse_error(message: str) -> str:
    return _sse({"type": "error", "errorText": message})


def _sse_done() -> str:
    return "data: [DONE]\n\n"


def _usage_payload(text: str, backend: str, model: str) -> dict[str, Any]:
    output_tokens = _approx_tokens(text)
    return {
        "backend": backend,
        "model": model,
        "outputTokens": output_tokens,
        "tokens": output_tokens,
    }


def _record_usage(
    db: Database,
    *,
    task_type: str,
    text: str,
    backend: str,
    model: str,
    metadata: dict[str, Any],
) -> None:
    try:
        SourceCatalogRepository(db).record_usage_event(
            UsageEvent(
                task_type=task_type,
                backend=backend,
                model=model,
                output_tokens=_approx_tokens(text),
                metadata=metadata,
            )
        )
    except Exception:
        logger.warning("Failed to record chat usage", exc_info=True)


def _approx_tokens(text: str) -> int:
    return max(1, len(text or "") // 4) if text else 0


def _tool_status(tool_name: str, args: dict[str, Any]) -> str:
    if tool_name == "search_sources":
        return f"Searching vault for \"{args.get('query', '')}\"..."
    if tool_name == "read_source":
        return f"Reading source {args.get('source_id', '')}..."
    if tool_name == "read_note":
        return f"Reading note {args.get('path', '')}..."
    if tool_name == "list_sources":
        return "Listing sources..."
    if tool_name == "list_knowledge":
        return "Browsing topics, entities, and concepts..."
    if tool_name == "get_source_relations":
        return f"Finding relations for {args.get('source_id', '')}..."
    return f"Running {tool_name}..."


def _compact_tool_output(output: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(output, ensure_ascii=False)
    if len(text) <= 2000:
        return output
    return {"preview": text[:2000], "truncated": True}


def _resolve_vault_path(vault_path: Path, relative_path: str) -> Path | None:
    root = vault_path.expanduser().resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _truncate_chars(text: str, max_chars: int) -> str:
    if len(text or "") <= max_chars:
        return text or ""
    return (text or "")[: max_chars - 1].rstrip() + "..."


def _json_list(value: Any) -> list[dict[str, Any]]:
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _clean_title(title: str) -> str:
    return _truncate_chars(title.strip() or "New conversation", 80)


def _title_from_message(message: str) -> str:
    title = re.sub(r"\s+", " ", message).strip()
    return _clean_title(title[:60])


def _mask_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "********"
    return f"{api_key[:4]}...{api_key[-4:]}"


def _first_backend(raw: str) -> str:
    for token in raw.split(","):
        normalized = token.strip().lower()
        if normalized in CHAT_BACKEND_ORDER:
            return normalized
    return BackendType.API.value
