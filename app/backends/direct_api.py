"""Direct API backend — calls OpenAI-compatible chat/completions endpoints."""

from __future__ import annotations

import logging

from langchain_openai import ChatOpenAI

from app.backends.base import ReasoningBackend
from app.backends.models import (
    BackendDescriptor,
    BackendRequest,
    BackendResponse,
    BackendType,
    TaskName,
)

logger = logging.getLogger(__name__)


class DirectApiBackend(ReasoningBackend):
    """Backend that calls any OpenAI-compatible API directly."""

    def __init__(
        self,
        *,
        api_key: str = "",
        base_url: str = "",
        model: str = "",
        temperature: float = 0.2,
        task_overrides: dict[TaskName, dict] | None = None,
    ):
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._temperature = temperature
        self._task_overrides = task_overrides or {}
        self._clients: dict[str, ChatOpenAI] = {}

    def _resolve(self, task: TaskName | None) -> tuple[str, str, str]:
        """Resolve api_key, base_url, model for a given task (with overrides)."""
        ovr = self._task_overrides.get(task, {}) if task else {}
        api_key = ovr.get("api_key") or self._api_key
        base_url = ovr.get("base_url") or self._base_url
        model = ovr.get("model") or self._model
        return api_key, base_url, model

    def _get_client(self, task: TaskName | None = None) -> ChatOpenAI:
        api_key, base_url, model = self._resolve(task)
        cache_key = f"{base_url}|{model}|{api_key[:8]}"
        if cache_key not in self._clients:
            kwargs: dict = {
                "model": model,
                "api_key": api_key,
                "temperature": self._temperature,
            }
            if base_url:
                kwargs["base_url"] = base_url
            self._clients[cache_key] = ChatOpenAI(**kwargs)
        return self._clients[cache_key]

    def is_available(self, task: TaskName | None = None) -> bool:
        api_key, _, model = self._resolve(task)
        return bool(api_key and model)

    def describe(self, task: TaskName | None = None) -> BackendDescriptor:
        api_key, base_url, model = self._resolve(task)
        available = bool(api_key and model)
        reason = ""
        if not api_key:
            reason = "API key not configured"
        elif not model:
            reason = "Model not configured"
        return BackendDescriptor(
            backend_type=BackendType.API,
            model=model,
            provider=base_url or "openai",
            available=available,
            reason=reason,
        )

    async def generate(self, request: BackendRequest) -> BackendResponse:
        if not self.is_available(request.task):
            desc = self.describe(request.task)
            return BackendResponse(
                success=False,
                error=f"API backend unavailable: {desc.reason}",
                backend_used=BackendType.API,
            )

        _, _, model = self._resolve(request.task)
        client = self._get_client(request.task)

        messages: list[dict] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.user_prompt})

        try:
            resp = await client.ainvoke(messages)
            text = resp.content if isinstance(resp.content, str) else str(resp.content)
            return BackendResponse(
                text=text,
                backend_used=BackendType.API,
                model_used=model,
                success=True,
            )
        except Exception as exc:
            logger.error("API backend call failed (model=%s): %s", model, exc)
            return BackendResponse(
                success=False,
                error=str(exc),
                backend_used=BackendType.API,
                model_used=model,
            )
