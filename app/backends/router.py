"""Backend router — selects the best backend for each task with fallback."""

from __future__ import annotations

import logging

from pydantic import BaseModel

from app.backends.base import ReasoningBackend
from app.backends.models import (
    BackendDescriptor,
    BackendRequest,
    BackendResponse,
    TaskName,
)

logger = logging.getLogger(__name__)

DEFAULT_FALLBACK_ORDER: list[str] = [
    "api",
    "opencode",
    "claude_code",
    "codex",
]


class BackendRouter:
    """Routes requests to the best available backend, with per-task fallback."""

    def __init__(
        self,
        backends: dict[str, ReasoningBackend],
        task_orders: dict[TaskName, list[str]] | None = None,
        default_order: list[str] | None = None,
    ):
        self._backends = backends
        self._task_orders = task_orders or {}
        self._default_order = default_order or DEFAULT_FALLBACK_ORDER

    def _get_order(self, task: TaskName) -> list[str]:
        return self._task_orders.get(task, self._default_order)

    def select_backend(self, task: TaskName) -> tuple[ReasoningBackend | None, list[str]]:
        """Pick the first available backend for *task*. Returns (backend, skip_reasons)."""
        order = self._get_order(task)
        skip_reasons: list[str] = []

        for backend_id in order:
            backend = self._backends.get(backend_id)
            if backend is None:
                skip_reasons.append(f"{backend_id}: not registered")
                continue
            if not backend.is_available(task):
                desc = backend.describe(task)
                skip_reasons.append(f"{backend_id}: {desc.reason or 'unavailable'}")
                continue
            if skip_reasons:
                logger.info(
                    "Backend fallback for task=%s: using %s (skipped: %s)",
                    task.value,
                    backend_id,
                    "; ".join(skip_reasons),
                )
            else:
                logger.debug("Backend selected for task=%s: %s", task.value, backend_id)
            return backend, skip_reasons

        return None, skip_reasons

    async def generate(self, request: BackendRequest) -> BackendResponse:
        """Route a generation request with selection-time and execution-time fallback."""
        order = self._get_order(request.task)
        all_reasons: list[str] = []

        for backend_id in order:
            backend = self._backends.get(backend_id)
            if backend is None:
                all_reasons.append(f"{backend_id}: not registered")
                continue
            if not backend.is_available(request.task):
                desc = backend.describe(request.task)
                all_reasons.append(f"{backend_id}: {desc.reason or 'unavailable'}")
                continue

            logger.info("Trying backend %s for task=%s", backend_id, request.task.value)
            response = await backend.generate(request)

            if response.success:
                response.was_fallback = len(all_reasons) > 0
                response.fallback_reasons = list(all_reasons)
                return response

            all_reasons.append(f"{backend_id}: execution failed - {response.error}")
            logger.info(
                "Backend %s failed for task=%s: %s — trying next",
                backend_id,
                request.task.value,
                response.error,
            )

        error_summary = "; ".join(all_reasons) if all_reasons else "No backends configured"
        logger.error("All backends exhausted for task=%s: %s", request.task.value, error_summary)
        return BackendResponse(
            success=False,
            error=f"All backends failed: {error_summary}",
            fallback_reasons=all_reasons,
        )

    async def generate_structured(
        self,
        request: BackendRequest,
        schema_class: type[BaseModel] | None = None,
    ) -> BackendResponse:
        """Route a structured-output request with fallback at both selection and execution time."""
        order = self._get_order(request.task)
        all_reasons: list[str] = []

        for backend_id in order:
            backend = self._backends.get(backend_id)
            if backend is None:
                all_reasons.append(f"{backend_id}: not registered")
                continue
            if not backend.is_available(request.task):
                desc = backend.describe(request.task)
                all_reasons.append(f"{backend_id}: {desc.reason or 'unavailable'}")
                continue

            logger.info(
                "Trying backend %s for structured task=%s",
                backend_id,
                request.task.value,
            )
            response = await backend.generate_structured(request, schema_class=schema_class)

            if response.success:
                response.was_fallback = len(all_reasons) > 0
                response.fallback_reasons = list(all_reasons)
                return response

            all_reasons.append(f"{backend_id}: {response.error}")
            logger.info(
                "Backend %s structured output failed for task=%s: %s",
                backend_id,
                request.task.value,
                response.error,
            )

        error_summary = "; ".join(all_reasons) if all_reasons else "No backends configured"
        return BackendResponse(
            success=False,
            error=f"All backends failed for structured output: {error_summary}",
            fallback_reasons=all_reasons,
        )

    def describe_all(self, task: TaskName) -> list[BackendDescriptor]:
        """Return descriptors for all backends in order for a task."""
        order = self._get_order(task)
        result = []
        for backend_id in order:
            backend = self._backends.get(backend_id)
            if backend:
                result.append(backend.describe(task))
            else:
                result.append(
                    BackendDescriptor(
                        backend_type=backend_id,
                        available=False,
                        reason="not registered",
                    )
                )
        return result
