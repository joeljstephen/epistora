"""OpenCode CLI backend — shells out to `opencode` in non-interactive mode."""

from __future__ import annotations

import asyncio
import logging
import shutil

from app.backends.base import ReasoningBackend
from app.backends.models import (
    BackendDescriptor,
    BackendRequest,
    BackendResponse,
    BackendType,
    TaskName,
)

logger = logging.getLogger(__name__)


class OpenCodeCliBackend(ReasoningBackend):
    """Backend that executes prompts via the OpenCode CLI."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        binary: str = "opencode",
        model: str = "",
        timeout_seconds: int = 180,
        task_models: dict[TaskName, str] | None = None,
    ):
        self._enabled = enabled
        self._binary = binary
        self._model = model
        self._timeout = timeout_seconds
        self._task_models = task_models or {}

    def _resolve_model(self, task: TaskName | None) -> str:
        if task and task in self._task_models and self._task_models[task]:
            return self._task_models[task]
        return self._model

    def _find_binary(self) -> str | None:
        return shutil.which(self._binary)

    def is_available(self, task: TaskName | None = None) -> bool:
        if not self._enabled:
            return False
        return self._find_binary() is not None

    def describe(self, task: TaskName | None = None) -> BackendDescriptor:
        binary_path = self._find_binary()
        available = self._enabled and binary_path is not None
        reason = ""
        if not self._enabled:
            reason = "OpenCode backend disabled"
        elif not binary_path:
            reason = f"'{self._binary}' binary not found in PATH"
        elif available:
            reason = "binary found; provider auth/session not verified until execution"
        return BackendDescriptor(
            backend_type=BackendType.OPENCODE,
            model=self._resolve_model(task),
            provider="opencode",
            available=available,
            reason=reason,
        )

    async def generate(self, request: BackendRequest) -> BackendResponse:
        if not self.is_available(request.task):
            desc = self.describe(request.task)
            return BackendResponse(
                success=False,
                error=f"OpenCode backend unavailable: {desc.reason}",
                backend_used=BackendType.OPENCODE,
            )

        model = self._resolve_model(request.task)
        binary = self._find_binary()

        prompt = ""
        if request.system_prompt:
            prompt += f"[System]\n{request.system_prompt}\n\n"
        prompt += request.user_prompt

        if request.json_schema_hint:
            prompt += (
                "\n\nIMPORTANT: Respond ONLY with valid JSON matching this schema. "
                "No markdown fences, no extra text.\n"
                f"Schema: {request.json_schema_hint}"
            )

        # `opencode run` accepts the message as a positional argument.
        cmd = [binary, "run"]
        if model:
            cmd.extend(["--model", model])
        cmd.append(prompt)

        logger.info("OpenCode: executing %s (model=%s, timeout=%ds)", binary, model, self._timeout)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)

            stdout_text = stdout.decode("utf-8", errors="replace").strip()
            stderr_text = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode != 0:
                logger.error("OpenCode exited %d: %s", proc.returncode, stderr_text)
                return BackendResponse(
                    success=False,
                    error=f"OpenCode exited with code {proc.returncode}: {stderr_text[:500]}",
                    backend_used=BackendType.OPENCODE,
                    model_used=model,
                )

            return BackendResponse(
                text=stdout_text,
                backend_used=BackendType.OPENCODE,
                model_used=model,
                success=True,
            )

        except asyncio.TimeoutError:
            logger.error("OpenCode timed out after %ds", self._timeout)
            return BackendResponse(
                success=False,
                error=f"OpenCode timed out after {self._timeout}s",
                backend_used=BackendType.OPENCODE,
                model_used=model,
            )
        except Exception as exc:
            logger.error("OpenCode execution failed: %s", exc)
            return BackendResponse(
                success=False,
                error=str(exc),
                backend_used=BackendType.OPENCODE,
                model_used=model,
            )
