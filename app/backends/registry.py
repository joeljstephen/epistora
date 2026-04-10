"""Factory registry for reasoning backends."""

from __future__ import annotations

import logging
from collections.abc import Callable

from app.backends.claude_code_cli import ClaudeCodeCliBackend
from app.backends.codex_cli import CodexCliBackend
from app.backends.direct_api import DirectApiBackend
from app.backends.models import BackendType, TaskName
from app.backends.opencode_cli import OpenCodeCliBackend
from app.config import Settings
from app.plugins.loader import plugin_factories

logger = logging.getLogger(__name__)

BackendFactory = Callable[[Settings], object]

_BACKEND_FACTORIES: dict[str, BackendFactory] = {}
_BUILTIN_BACKEND_ORDER = [
    BackendType.API.value,
    BackendType.OPENCODE.value,
    BackendType.CLAUDE_CODE.value,
    BackendType.CODEX.value,
]


def register_backend(backend_id: str, factory: BackendFactory) -> None:
    _BACKEND_FACTORIES[backend_id] = factory


def builtin_backend_order() -> list[str]:
    _register_builtin_backends()
    return list(_BUILTIN_BACKEND_ORDER)


def build_backends(settings: Settings) -> dict[str, object]:
    _register_builtin_backends()
    factories = dict(_BACKEND_FACTORIES)
    factories.update(plugin_factories("reasoning_backend", settings))
    backends: dict[str, object] = {}
    for backend_id, factory in factories.items():
        try:
            backends[backend_id] = factory(settings)
        except Exception as exc:  # pragma: no cover - defensive isolation
            logger.warning(
                "Failed to initialize reasoning_backend plugin '%s': %s",
                backend_id,
                exc,
            )
    return backends


def _register_builtin_backends() -> None:
    if _BACKEND_FACTORIES:
        return

    register_backend(BackendType.API.value, _build_api_backend)
    register_backend(BackendType.OPENCODE.value, _build_opencode_backend)
    register_backend(BackendType.CLAUDE_CODE.value, _build_claude_code_backend)
    register_backend(BackendType.CODEX.value, _build_codex_backend)


def _build_api_backend(settings: Settings) -> DirectApiBackend:
    api_key = settings.effective_api_key()
    api_model = settings.effective_api_model()
    task_overrides: dict[TaskName, dict] = {}
    for task, suffix in [
        (TaskName.INGEST, "ingest"),
        (TaskName.QUERY, "query"),
        (TaskName.LINT, "lint"),
    ]:
        override: dict[str, str] = {}
        key = getattr(settings, f"api_api_key_{suffix}", "")
        url = getattr(settings, f"api_base_url_{suffix}", "")
        model = getattr(settings, f"api_model_{suffix}", "")
        if key:
            override["api_key"] = key
        if url:
            override["base_url"] = url
        if model:
            override["model"] = model
        if override:
            task_overrides[task] = override

    return DirectApiBackend(
        api_key=api_key,
        base_url=settings.api_base_url,
        model=api_model,
        temperature=settings.api_temperature,
        task_overrides=task_overrides,
    )


def _build_opencode_backend(settings: Settings) -> OpenCodeCliBackend:
    task_models: dict[TaskName, str] = {}
    if settings.opencode_model_ingest:
        task_models[TaskName.INGEST] = settings.opencode_model_ingest
    if settings.opencode_model_query:
        task_models[TaskName.QUERY] = settings.opencode_model_query
    if settings.opencode_model_lint:
        task_models[TaskName.LINT] = settings.opencode_model_lint

    return OpenCodeCliBackend(
        enabled=settings.opencode_enabled,
        binary=settings.opencode_binary,
        model=settings.opencode_model,
        timeout_seconds=settings.opencode_timeout_seconds,
        task_models=task_models,
    )


def _build_claude_code_backend(settings: Settings) -> ClaudeCodeCliBackend:
    task_models: dict[TaskName, str] = {}
    if settings.claude_code_model_ingest:
        task_models[TaskName.INGEST] = settings.claude_code_model_ingest
    if settings.claude_code_model_query:
        task_models[TaskName.QUERY] = settings.claude_code_model_query
    if settings.claude_code_model_lint:
        task_models[TaskName.LINT] = settings.claude_code_model_lint

    return ClaudeCodeCliBackend(
        enabled=settings.claude_code_enabled,
        binary=settings.claude_code_binary,
        model=settings.claude_code_model,
        timeout_seconds=settings.claude_code_timeout_seconds,
        task_models=task_models,
    )


def _build_codex_backend(settings: Settings) -> CodexCliBackend:
    task_models: dict[TaskName, str] = {}
    if settings.codex_model_ingest:
        task_models[TaskName.INGEST] = settings.codex_model_ingest
    if settings.codex_model_query:
        task_models[TaskName.QUERY] = settings.codex_model_query
    if settings.codex_model_lint:
        task_models[TaskName.LINT] = settings.codex_model_lint

    return CodexCliBackend(
        enabled=settings.codex_enabled,
        binary=settings.codex_binary,
        model=settings.codex_model,
        timeout_seconds=settings.codex_timeout_seconds,
        task_models=task_models,
    )
