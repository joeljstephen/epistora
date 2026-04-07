"""LLM client initialisation and backend router factory.

The legacy ``get_llm()`` still works for any code that needs a raw LangChain
ChatOpenAI client.  New code should prefer ``get_backend_router()`` which
provides multi-backend, per-task routing with automatic fallback.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.backends.claude_code_cli import ClaudeCodeCliBackend
from app.backends.direct_api import DirectApiBackend
from app.backends.models import BackendRequest, BackendResponse, BackendType, TaskName
from app.backends.opencode_cli import OpenCodeCliBackend
from app.backends.router import BackendRouter
from app.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_llm() -> ChatOpenAI:
    """Legacy single-client accessor — kept for backward compatibility."""
    settings = get_settings()
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0.2,
    )


def _parse_order(raw: str) -> list[BackendType]:
    mapping = {
        "api": BackendType.API,
        "opencode": BackendType.OPENCODE,
        "open_code": BackendType.OPENCODE,
        "claude_code": BackendType.CLAUDE_CODE,
        "claude-code": BackendType.CLAUDE_CODE,
        "claude": BackendType.CLAUDE_CODE,
    }
    ordered: list[BackendType] = []
    for token in raw.split(","):
        normalized = token.strip().lower()
        backend_type = mapping.get(normalized)
        if backend_type and backend_type not in ordered:
            ordered.append(backend_type)
    return ordered or [BackendType.API, BackendType.OPENCODE, BackendType.CLAUDE_CODE]


_router: BackendRouter | None = None


def get_backend_router() -> BackendRouter:
    """Build (and cache) a BackendRouter from current settings."""
    global _router
    if _router is not None:
        return _router

    settings = get_settings()

    # --- Direct API backend ---
    api_key = settings.effective_api_key()
    api_model = settings.effective_api_model()
    task_overrides: dict[TaskName, dict] = {}
    for task, suffix in [
        (TaskName.INGEST, "ingest"),
        (TaskName.QUERY, "query"),
        (TaskName.LINT, "lint"),
    ]:
        ovr: dict = {}
        key = getattr(settings, f"api_api_key_{suffix}", "")
        url = getattr(settings, f"api_base_url_{suffix}", "")
        model = getattr(settings, f"api_model_{suffix}", "")
        if key:
            ovr["api_key"] = key
        if url:
            ovr["base_url"] = url
        if model:
            ovr["model"] = model
        if ovr:
            task_overrides[task] = ovr

    api_backend = DirectApiBackend(
        api_key=api_key,
        base_url=settings.api_base_url,
        model=api_model,
        temperature=settings.api_temperature,
        task_overrides=task_overrides,
    )

    # --- OpenCode CLI backend ---
    oc_task_models: dict[TaskName, str] = {}
    if settings.opencode_model_ingest:
        oc_task_models[TaskName.INGEST] = settings.opencode_model_ingest
    if settings.opencode_model_query:
        oc_task_models[TaskName.QUERY] = settings.opencode_model_query
    if settings.opencode_model_lint:
        oc_task_models[TaskName.LINT] = settings.opencode_model_lint

    opencode_backend = OpenCodeCliBackend(
        enabled=settings.opencode_enabled,
        binary=settings.opencode_binary,
        model=settings.opencode_model,
        timeout_seconds=settings.opencode_timeout_seconds,
        task_models=oc_task_models,
    )

    # --- Claude Code CLI backend ---
    cc_task_models: dict[TaskName, str] = {}
    if settings.claude_code_model_ingest:
        cc_task_models[TaskName.INGEST] = settings.claude_code_model_ingest
    if settings.claude_code_model_query:
        cc_task_models[TaskName.QUERY] = settings.claude_code_model_query
    if settings.claude_code_model_lint:
        cc_task_models[TaskName.LINT] = settings.claude_code_model_lint

    claude_backend = ClaudeCodeCliBackend(
        enabled=settings.claude_code_enabled,
        binary=settings.claude_code_binary,
        model=settings.claude_code_model,
        timeout_seconds=settings.claude_code_timeout_seconds,
        task_models=cc_task_models,
    )

    backends = {
        BackendType.API: api_backend,
        BackendType.OPENCODE: opencode_backend,
        BackendType.CLAUDE_CODE: claude_backend,
    }

    task_orders: dict[TaskName, list[BackendType]] = {
        TaskName.INGEST: _parse_order(settings.backend_order_ingest),
        TaskName.QUERY: _parse_order(settings.backend_order_query),
        TaskName.LINT: _parse_order(settings.backend_order_lint),
    }

    _router = BackendRouter(backends=backends, task_orders=task_orders)
    logger.info("Backend router initialized with %d backends", len(backends))
    return _router


def reset_backend_router() -> None:
    """Clear the cached router (for tests or config changes)."""
    global _router
    _router = None


async def run_text(task: TaskName, system_prompt: str, user_prompt: str) -> BackendResponse:
    """Convenience: route a plain text generation through the backend router."""
    router = get_backend_router()
    request = BackendRequest(
        task=task,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    return await router.generate(request)


async def run_structured(
    task: TaskName,
    system_prompt: str,
    user_prompt: str,
    json_schema_hint: str = "",
) -> BackendResponse:
    """Convenience: route a structured (JSON) generation through the backend router."""
    router = get_backend_router()
    request = BackendRequest(
        task=task,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        json_schema_hint=json_schema_hint,
    )
    return await router.generate_structured(request)
