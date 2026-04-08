"""OpenCode CLI backend — shells out to `opencode` using a pseudo-TTY.

OpenCode's `run` command requires a real TTY to produce output; piped
stdout/stderr stay empty indefinitely.  We allocate a pty.openpty() pair,
attach the slave end to the subprocess, and read from the master end in a
thread via run_in_executor so the event loop stays unblocked.
"""

from __future__ import annotations

import asyncio
import logging
import os
import pty
import re
import select
import shutil
import subprocess
import time

from app.backends.base import ReasoningBackend
from app.backends.models import (
    BackendDescriptor,
    BackendRequest,
    BackendResponse,
    BackendType,
    TaskName,
)

logger = logging.getLogger(__name__)

# Matches common ANSI/VT100 escape sequences including OSC strings
_ANSI_RE = re.compile(
    r"\x1b(?:"
    r"\[[0-9;]*[a-zA-Z]"       # CSI sequences  e.g. [0m [2J
    r"|\][^\x07]*(?:\x07|\x1b\\)"  # OSC sequences e.g. ]0;title BEL
    r"|[()][AB012]"             # Charset designations
    r"|[ABCDEFGHIJKLMNOPQRSTUVWXYZ\\]"  # Fe/Fp sequences
    r")"
)
# OpenCode prints status lines like "> build · model-name" or "> thinking"
_STATUS_LINE_RE = re.compile(r"^>.*", re.MULTILINE)


def _pty_run_sync(cmd: list[str], timeout: float) -> tuple[str, int]:
    """Run *cmd* with a pseudo-TTY and return (stdout_text, return_code).

    Raises TimeoutError if the process doesn't complete within *timeout* seconds.
    """
    master_fd, slave_fd = pty.openpty()

    proc = subprocess.Popen(
        cmd,
        stdout=slave_fd,
        stderr=slave_fd,
        stdin=slave_fd,
        close_fds=True,
    )
    os.close(slave_fd)

    output = b""
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        r, _, _ = select.select([master_fd], [], [], min(0.5, remaining))
        if r:
            try:
                chunk = os.read(master_fd, 4096)
                if chunk:
                    output += chunk
                else:
                    break
            except OSError:
                break

        if proc.poll() is not None:
            # Drain any remaining data
            while True:
                try:
                    r2, _, _ = select.select([master_fd], [], [], 0.1)
                    if not r2:
                        break
                    chunk = os.read(master_fd, 4096)
                    if not chunk:
                        break
                    output += chunk
                except OSError:
                    break
            break
    else:
        proc.kill()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.close(master_fd)
        except OSError:
            pass
        raise TimeoutError(f"opencode did not respond within {timeout:.0f}s")

    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()

    try:
        os.close(master_fd)
    except OSError:
        pass

    text = output.decode("utf-8", errors="replace")
    text = _ANSI_RE.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _STATUS_LINE_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, proc.returncode or 0


class OpenCodeCliBackend(ReasoningBackend):
    """Backend that executes prompts via the OpenCode CLI using a pseudo-TTY."""

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

        cmd = [binary, "run"]
        if model:
            cmd.extend(["--model", model])
        cmd.append(prompt)

        logger.info(
            "OpenCode: executing %s (model=%s, timeout=%ds, prompt_len=%d)",
            binary, model, self._timeout, len(prompt),
        )

        loop = asyncio.get_event_loop()
        try:
            stdout_text, returncode = await asyncio.wait_for(
                loop.run_in_executor(None, _pty_run_sync, cmd, float(self._timeout)),
                timeout=self._timeout + 15,
            )
        except (asyncio.TimeoutError, TimeoutError):
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

        if returncode != 0:
            logger.error("OpenCode exited %d", returncode)
            return BackendResponse(
                success=False,
                error=f"OpenCode exited with code {returncode}",
                backend_used=BackendType.OPENCODE,
                model_used=model,
            )

        if not stdout_text:
            return BackendResponse(
                success=False,
                error="OpenCode produced no output",
                backend_used=BackendType.OPENCODE,
                model_used=model,
            )

        logger.info(
            "OpenCode: completed (model=%s, output_len=%d)", model, len(stdout_text)
        )
        return BackendResponse(
            text=stdout_text,
            backend_used=BackendType.OPENCODE,
            model_used=model,
            success=True,
        )
