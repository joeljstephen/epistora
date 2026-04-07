"""Claude Code CLI backend — shells out to `claude -p` in print/non-interactive mode."""

from __future__ import annotations

import asyncio
import json
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


class ClaudeCodeCliBackend(ReasoningBackend):
    """Backend that executes prompts via the Claude Code CLI in print mode."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        binary: str = "claude",
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

    @staticmethod
    def _build_prompt(request: BackendRequest, structured: bool = False) -> str:
        prompt = request.user_prompt
        if (
            structured
            and request.json_schema_hint
            and not _is_json_schema(request.json_schema_hint)
        ):
            prompt += (
                "\n\nIMPORTANT: Respond ONLY with valid JSON matching this schema. "
                "No markdown fences, no extra text.\n"
                f"Schema: {request.json_schema_hint}"
            )
        return prompt

    def _build_command(
        self, request: BackendRequest, structured: bool = False
    ) -> tuple[list[str], str]:
        model = self._resolve_model(request.task)
        prompt = self._build_prompt(request, structured=structured)

        cmd = [
            self._find_binary(),
            "--print",
            "--output-format",
            "text",
            "--tools",
            "",
        ]
        if request.system_prompt:
            cmd.extend(["--system-prompt", request.system_prompt])
        if model:
            cmd.extend(["--model", model])
        if structured and request.json_schema_hint and _is_json_schema(request.json_schema_hint):
            cmd.extend(["--json-schema", request.json_schema_hint])
        cmd.append(prompt)
        return cmd, model

    async def _execute(
        self,
        cmd: list[str],
        model: str,
        structured: bool = False,
    ) -> BackendResponse:
        label = "structured" if structured else "text"
        logger.info(
            "Claude Code: executing %s request (model=%s, timeout=%ds)",
            label,
            model,
            self._timeout,
        )

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
                logger.error("Claude Code exited %d: %s", proc.returncode, stderr_text)
                return BackendResponse(
                    success=False,
                    error=f"Claude Code exited with code {proc.returncode}: {stderr_text[:500]}",
                    backend_used=BackendType.CLAUDE_CODE,
                    model_used=model,
                )

            return BackendResponse(
                text=stdout_text,
                backend_used=BackendType.CLAUDE_CODE,
                model_used=model,
                success=True,
            )

        except asyncio.TimeoutError:
            logger.error("Claude Code timed out after %ds", self._timeout)
            return BackendResponse(
                success=False,
                error=f"Claude Code timed out after {self._timeout}s",
                backend_used=BackendType.CLAUDE_CODE,
                model_used=model,
            )
        except Exception as exc:
            logger.error("Claude Code execution failed: %s", exc)
            return BackendResponse(
                success=False,
                error=str(exc),
                backend_used=BackendType.CLAUDE_CODE,
                model_used=model,
            )

    def is_available(self, task: TaskName | None = None) -> bool:
        if not self._enabled:
            return False
        return self._find_binary() is not None

    def describe(self, task: TaskName | None = None) -> BackendDescriptor:
        binary_path = self._find_binary()
        available = self._enabled and binary_path is not None
        reason = ""
        if not self._enabled:
            reason = "Claude Code backend disabled"
        elif not binary_path:
            reason = f"'{self._binary}' binary not found in PATH"
        elif available:
            reason = "binary found; provider auth/session not verified until execution"
        return BackendDescriptor(
            backend_type=BackendType.CLAUDE_CODE,
            model=self._resolve_model(task),
            provider="claude_code",
            available=available,
            reason=reason,
        )

    async def generate(self, request: BackendRequest) -> BackendResponse:
        if not self.is_available(request.task):
            desc = self.describe(request.task)
            return BackendResponse(
                success=False,
                error=f"Claude Code backend unavailable: {desc.reason}",
                backend_used=BackendType.CLAUDE_CODE,
            )

        cmd, model = self._build_command(request, structured=False)
        return await self._execute(cmd, model, structured=False)

    async def generate_structured(
        self,
        request: BackendRequest,
        schema_class=None,
    ) -> BackendResponse:
        if not self.is_available(request.task):
            desc = self.describe(request.task)
            return BackendResponse(
                success=False,
                error=f"Claude Code backend unavailable: {desc.reason}",
                backend_used=BackendType.CLAUDE_CODE,
            )

        cmd, model = self._build_command(request, structured=True)
        response = await self._execute(cmd, model, structured=True)
        if not response.success:
            return response

        from app.backends.base import _extract_json

        cleaned = _extract_json(response.text)
        if cleaned is None:
            response.success = False
            response.error = "Claude Code response did not contain valid JSON"
            return response

        if schema_class is not None:
            schema_class.model_validate_json(cleaned)

        response.text = cleaned
        return response


def _is_json_schema(value: str) -> bool:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return False
    return isinstance(parsed, dict)
