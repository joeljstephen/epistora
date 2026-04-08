"""Codex CLI backend — shells out to `codex exec` in non-interactive mode."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import tempfile
from pathlib import Path

from app.backends.base import ReasoningBackend, _extract_json
from app.backends.models import (
    BackendDescriptor,
    BackendRequest,
    BackendResponse,
    BackendType,
    TaskName,
)

logger = logging.getLogger(__name__)


class CodexCliBackend(ReasoningBackend):
    """Backend that executes prompts via the Codex CLI in exec mode."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        binary: str = "codex",
        model: str = "",
        timeout_seconds: int = 300,
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

    def _build_prompt(self, request: BackendRequest, *, structured: bool) -> str:
        prompt = request.user_prompt
        if request.system_prompt:
            prompt = f"[System]\n{request.system_prompt}\n\n{prompt}"
        if (
            structured
            and request.json_schema_hint
            and not self._looks_like_json_schema(request.json_schema_hint)
        ):
            prompt += (
                "\n\nIMPORTANT: Respond ONLY with valid JSON matching this schema. "
                "No markdown fences, no extra text.\n"
                f"Schema: {request.json_schema_hint}"
            )
        return prompt

    def _normalized_schema_hint(self, json_schema_hint: str) -> str:
        if not self._looks_like_json_schema(json_schema_hint):
            return json_schema_hint
        try:
            schema = json.loads(json_schema_hint)
        except json.JSONDecodeError:
            return json_schema_hint
        normalized = self._normalize_schema_object(schema)
        return json.dumps(normalized)

    def _normalize_schema_object(self, value):
        if isinstance(value, dict):
            normalized = {key: self._normalize_schema_object(inner) for key, inner in value.items()}
            if normalized.get("type") == "object":
                normalized["additionalProperties"] = False
            return normalized
        if isinstance(value, list):
            return [self._normalize_schema_object(item) for item in value]
        return value

    async def _run_exec(
        self,
        request: BackendRequest,
        *,
        structured: bool,
    ) -> BackendResponse:
        if not self.is_available(request.task):
            desc = self.describe(request.task)
            return BackendResponse(
                success=False,
                error=f"Codex backend unavailable: {desc.reason}",
                backend_used=BackendType.CODEX,
            )

        model = self._resolve_model(request.task)
        binary = self._find_binary()
        schema_hint = (
            self._normalized_schema_hint(request.json_schema_hint)
            if structured and request.json_schema_hint
            else request.json_schema_hint
        )
        effective_request = request.model_copy(update={"json_schema_hint": schema_hint})
        prompt = self._build_prompt(effective_request, structured=structured)

        with tempfile.TemporaryDirectory(prefix="epistora-codex-") as tmpdir:
            tmp_path = Path(tmpdir)
            output_path = tmp_path / "last-message.txt"

            cmd = [
                binary,
                "exec",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--output-last-message",
                str(output_path),
                "-C",
                tmpdir,
            ]
            if model:
                cmd.extend(["--model", model])

            if structured and schema_hint and self._looks_like_json_schema(
                schema_hint
            ):
                schema_path = tmp_path / "schema.json"
                schema_path.write_text(schema_hint, encoding="utf-8")
                cmd.extend(["--output-schema", str(schema_path)])

            cmd.append(prompt)

            logger.info(
                "Codex: executing request (model=%s, timeout=%ds, structured=%s)",
                model,
                self._timeout,
                structured,
            )

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
            except asyncio.TimeoutError:
                logger.error("Codex timed out after %ds", self._timeout)
                return BackendResponse(
                    success=False,
                    error=f"Codex timed out after {self._timeout}s",
                    backend_used=BackendType.CODEX,
                    model_used=model,
                )
            except Exception as exc:
                logger.error("Codex execution failed: %s", exc)
                return BackendResponse(
                    success=False,
                    error=str(exc),
                    backend_used=BackendType.CODEX,
                    model_used=model,
                )

            stderr_text = stderr.decode("utf-8", errors="replace").strip()
            if proc.returncode != 0:
                logger.error("Codex exited %d: %s", proc.returncode, stderr_text)
                return BackendResponse(
                    success=False,
                    error=f"Codex exited with code {proc.returncode}: {stderr_text[:500]}",
                    backend_used=BackendType.CODEX,
                    model_used=model,
                )

            try:
                text = output_path.read_text(encoding="utf-8").strip()
            except FileNotFoundError:
                text = ""

            if not text:
                return BackendResponse(
                    success=False,
                    error="Codex produced no output",
                    backend_used=BackendType.CODEX,
                    model_used=model,
                )

            return BackendResponse(
                text=text,
                backend_used=BackendType.CODEX,
                model_used=model,
                success=True,
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
            reason = "Codex backend disabled"
        elif not binary_path:
            reason = f"'{self._binary}' binary not found in PATH"
        elif available:
            reason = "binary found; provider auth/session not verified until execution"
        return BackendDescriptor(
            backend_type=BackendType.CODEX,
            model=self._resolve_model(task),
            provider="codex",
            available=available,
            reason=reason,
        )

    async def generate(self, request: BackendRequest) -> BackendResponse:
        return await self._run_exec(request, structured=False)

    async def generate_structured(
        self,
        request: BackendRequest,
        schema_class=None,
    ) -> BackendResponse:
        response = await self._run_exec(request, structured=True)
        if not response.success:
            return response

        cleaned = _extract_json(response.text)
        if cleaned is None:
            response.success = False
            response.error = "Codex response did not contain valid JSON"
            return response

        if schema_class is not None:
            schema_class.model_validate_json(cleaned)

        response.text = cleaned
        return response

    @staticmethod
    def _looks_like_json_schema(value: str) -> bool:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return False
        return isinstance(parsed, dict)
