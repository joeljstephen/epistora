"""Backend router factory and text-generation helpers."""

from __future__ import annotations

import logging

from app.backends.models import BackendRequest, BackendResponse, BackendType, TaskName
from app.backends.registry import build_backends, builtin_backend_order
from app.backends.router import BackendRouter
from app.config import get_settings

logger = logging.getLogger(__name__)

_BACKEND_ALIASES = {
    "api": BackendType.API.value,
    "codex": BackendType.CODEX.value,
    "opencode": BackendType.OPENCODE.value,
    "open_code": BackendType.OPENCODE.value,
    "claude_code": BackendType.CLAUDE_CODE.value,
    "claude-code": BackendType.CLAUDE_CODE.value,
    "claude": BackendType.CLAUDE_CODE.value,
}


def _parse_order(
    raw: str,
    *,
    known_backend_ids: set[str],
    strict: bool = False,
) -> list[str]:
    ordered: list[str] = []
    for token in raw.split(","):
        normalized = token.strip().lower()
        if not normalized:
            continue
        backend_id = _BACKEND_ALIASES.get(normalized, normalized)
        if backend_id not in known_backend_ids:
            message = f"Unknown backend token '{token.strip()}' in backend order '{raw}'"
            if strict:
                raise ValueError(message)
            logger.warning(message)
            continue
        if backend_id not in ordered:
            ordered.append(backend_id)

    if ordered:
        return ordered

    fallback = [
        backend_id for backend_id in builtin_backend_order() if backend_id in known_backend_ids
    ]
    if fallback:
        return fallback
    return list(known_backend_ids)


_router: BackendRouter | None = None


def get_backend_router() -> BackendRouter:
    """Build (and cache) a BackendRouter from current settings."""
    global _router
    if _router is not None:
        return _router

    settings = get_settings()
    backends = build_backends(settings)
    known_backend_ids = set(backends)

    task_orders: dict[TaskName, list[str]] = {
        TaskName.INGEST: _parse_order(
            settings.backend_order_ingest,
            known_backend_ids=known_backend_ids,
            strict=settings.backend_order_strict,
        ),
        TaskName.QUERY: _parse_order(
            settings.backend_order_query,
            known_backend_ids=known_backend_ids,
            strict=settings.backend_order_strict,
        ),
        TaskName.TOPIC_BUNDLE: _parse_order(
            settings.backend_order_query,
            known_backend_ids=known_backend_ids,
            strict=settings.backend_order_strict,
        ),
        TaskName.LINT: _parse_order(
            settings.backend_order_lint,
            known_backend_ids=known_backend_ids,
            strict=settings.backend_order_strict,
        ),
    }

    _router = BackendRouter(
        backends=backends,
        task_orders=task_orders,
        default_order=[
            backend_id for backend_id in builtin_backend_order() if backend_id in backends
        ],
    )
    logger.info("Backend router initialized with backends=%s", ",".join(backends))
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
