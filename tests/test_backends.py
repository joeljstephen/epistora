"""Tests for the backend abstraction layer: availability, routing, fallback, parsing."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.backends.base import ReasoningBackend, _extract_json
from app.backends.claude_code_cli import ClaudeCodeCliBackend
from app.backends.codex_cli import CodexCliBackend
from app.backends.direct_api import DirectApiBackend
from app.backends.models import (
    BackendDescriptor,
    BackendRequest,
    BackendResponse,
    BackendType,
    TaskName,
)
from app.backends.opencode_cli import OpenCodeCliBackend
from app.backends.router import BackendRouter
from app.compiler.llm import _parse_order

# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------


class TestExtractJson:
    def test_plain_json(self):
        assert _extract_json('{"a": 1}') == '{"a": 1}'

    def test_json_in_fences(self):
        raw = '```json\n{"a": 1}\n```'
        result = _extract_json(raw)
        assert json.loads(result) == {"a": 1}

    def test_json_embedded_in_text(self):
        raw = 'Here is the result:\n{"a": 1}\nDone.'
        result = _extract_json(raw)
        assert json.loads(result) == {"a": 1}

    def test_no_json(self):
        assert _extract_json("no json here") is None

    def test_array(self):
        assert _extract_json("[1, 2, 3]") == "[1, 2, 3]"


# ---------------------------------------------------------------------------
# Direct API backend
# ---------------------------------------------------------------------------


class TestDirectApiBackend:
    def test_available_when_configured(self):
        backend = DirectApiBackend(api_key="sk-test", model="gpt-4o")
        assert backend.is_available() is True
        assert backend.is_available(TaskName.INGEST) is True

    def test_unavailable_without_key(self):
        backend = DirectApiBackend(api_key="", model="gpt-4o")
        assert backend.is_available() is False

    def test_unavailable_without_model(self):
        backend = DirectApiBackend(api_key="sk-test", model="")
        assert backend.is_available() is False

    def test_describe_missing_key(self):
        backend = DirectApiBackend(api_key="", model="gpt-4o")
        desc = backend.describe()
        assert desc.available is False
        assert "key" in desc.reason.lower()

    def test_task_override(self):
        backend = DirectApiBackend(
            api_key="sk-global",
            model="gpt-4o",
            task_overrides={
                TaskName.INGEST: {"model": "glm-4", "api_key": "sk-ingest"},
            },
        )
        assert backend.is_available(TaskName.INGEST) is True
        desc = backend.describe(TaskName.INGEST)
        assert desc.model == "glm-4"

    @pytest.mark.asyncio
    async def test_generate_returns_error_when_unavailable(self):
        backend = DirectApiBackend(api_key="", model="")
        request = BackendRequest(task=TaskName.QUERY, user_prompt="hello")
        resp = await backend.generate(request)
        assert resp.success is False
        assert "unavailable" in resp.error.lower()


# ---------------------------------------------------------------------------
# OpenCode CLI backend
# ---------------------------------------------------------------------------


class TestOpenCodeCliBackend:
    def test_unavailable_when_disabled(self):
        backend = OpenCodeCliBackend(enabled=False)
        assert backend.is_available() is False

    @patch("shutil.which", return_value=None)
    def test_unavailable_when_binary_missing(self, _mock):
        backend = OpenCodeCliBackend(enabled=True)
        assert backend.is_available() is False
        desc = backend.describe()
        assert "not found" in desc.reason

    @patch("shutil.which", return_value="/usr/local/bin/opencode")
    def test_available_when_binary_exists(self, _mock):
        backend = OpenCodeCliBackend(enabled=True)
        assert backend.is_available() is True

    def test_task_model_resolution(self):
        backend = OpenCodeCliBackend(
            model="default-model",
            task_models={TaskName.INGEST: "ingest-model"},
        )
        assert backend._resolve_model(TaskName.INGEST) == "ingest-model"
        assert backend._resolve_model(TaskName.QUERY) == "default-model"

    @patch("shutil.which", return_value=None)
    @pytest.mark.asyncio
    async def test_generate_fails_when_binary_missing(self, _mock):
        backend = OpenCodeCliBackend(enabled=True)
        request = BackendRequest(task=TaskName.INGEST, user_prompt="test")
        resp = await backend.generate(request)
        assert resp.success is False

    @patch("shutil.which", return_value="/usr/local/bin/opencode")
    @pytest.mark.asyncio
    async def test_generate_uses_run_subcommand_message_positional(self, _mock):
        with patch(
            "app.backends.opencode_cli._pty_run_sync",
            return_value=("ok", 0),
        ) as mock_pty:
            backend = OpenCodeCliBackend(enabled=True, model="provider/model")
            request = BackendRequest(
                task=TaskName.QUERY,
                system_prompt="system",
                user_prompt="hello world",
            )
            resp = await backend.generate(request)

        assert resp.success is True
        args = mock_pty.call_args.args[0]
        assert args[:4] == [
            "/usr/local/bin/opencode",
            "run",
            "--model",
            "provider/model",
        ]
        assert args[-1] == "[System]\nsystem\n\nhello world"


# ---------------------------------------------------------------------------
# Claude Code CLI backend
# ---------------------------------------------------------------------------


class TestClaudeCodeCliBackend:
    def test_unavailable_when_disabled(self):
        backend = ClaudeCodeCliBackend(enabled=False)
        assert backend.is_available() is False

    @patch("shutil.which", return_value=None)
    def test_unavailable_when_binary_missing(self, _mock):
        backend = ClaudeCodeCliBackend(enabled=True)
        assert backend.is_available() is False
        desc = backend.describe()
        assert "not found" in desc.reason

    @patch("shutil.which", return_value="/usr/local/bin/claude")
    def test_available_when_binary_exists(self, _mock):
        backend = ClaudeCodeCliBackend(enabled=True)
        assert backend.is_available() is True

    def test_task_model_resolution(self):
        backend = ClaudeCodeCliBackend(
            model="default-model",
            task_models={TaskName.LINT: "lint-model"},
        )
        assert backend._resolve_model(TaskName.LINT) == "lint-model"
        assert backend._resolve_model(TaskName.QUERY) == "default-model"

    @patch("shutil.which", return_value="/usr/local/bin/claude")
    @pytest.mark.asyncio
    async def test_generate_structured_uses_native_json_schema(self, _mock):
        proc = AsyncMock()
        proc.communicate.return_value = (b'{"ok": true}', b"")
        proc.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=proc,
        ) as mock_exec:
            backend = ClaudeCodeCliBackend(enabled=True, model="sonnet")
            request = BackendRequest(
                task=TaskName.LINT,
                system_prompt="system",
                user_prompt="Return ok=true",
                json_schema_hint='{"type":"object","properties":{"ok":{"type":"boolean"}}}',
            )
            resp = await backend.generate_structured(request)

        assert resp.success is True
        args = mock_exec.await_args.args
        assert "--system-prompt" in args
        assert "--json-schema" in args
        assert "--tools" in args


# ---------------------------------------------------------------------------
# Codex CLI backend
# ---------------------------------------------------------------------------


class TestCodexCliBackend:
    def test_unavailable_when_disabled(self):
        backend = CodexCliBackend(enabled=False)
        assert backend.is_available() is False

    @patch("shutil.which", return_value=None)
    def test_unavailable_when_binary_missing(self, _mock):
        backend = CodexCliBackend(enabled=True)
        assert backend.is_available() is False
        desc = backend.describe()
        assert "not found" in desc.reason

    @patch("shutil.which", return_value="/usr/local/bin/codex")
    def test_available_when_binary_exists(self, _mock):
        backend = CodexCliBackend(enabled=True)
        assert backend.is_available() is True

    def test_task_model_resolution(self):
        backend = CodexCliBackend(
            model="default-model",
            task_models={TaskName.QUERY: "query-model"},
        )
        assert backend._resolve_model(TaskName.QUERY) == "query-model"
        assert backend._resolve_model(TaskName.INGEST) == "default-model"

    @patch("shutil.which", return_value="/usr/local/bin/codex")
    @pytest.mark.asyncio
    async def test_generate_uses_exec_output_file(self, _mock):
        proc = AsyncMock()
        proc.communicate.return_value = (b"", b"")
        proc.returncode = 0

        async def _fake_exec(*args, **kwargs):
            output_path = Path(args[args.index("--output-last-message") + 1])
            output_path.write_text("ok", encoding="utf-8")
            return proc

        with patch(
            "asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            side_effect=_fake_exec,
        ) as mock_exec:
            backend = CodexCliBackend(enabled=True, model="gpt-5")
            request = BackendRequest(task=TaskName.QUERY, user_prompt="hello")
            resp = await backend.generate(request)

        assert resp.success is True
        args = mock_exec.await_args.args
        assert args[:2] == ("/usr/local/bin/codex", "exec")
        assert "--output-last-message" in args
        assert "--sandbox" in args
        assert "read-only" in args

    @patch("shutil.which", return_value="/usr/local/bin/codex")
    @pytest.mark.asyncio
    async def test_generate_structured_uses_output_schema(self, _mock):
        proc = AsyncMock()
        proc.communicate.return_value = (b"", b"")
        proc.returncode = 0

        async def _fake_exec(*args, **kwargs):
            output_path = Path(args[args.index("--output-last-message") + 1])
            output_path.write_text('{"ok": true}', encoding="utf-8")
            return proc

        with patch(
            "asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            side_effect=_fake_exec,
        ) as mock_exec:
            backend = CodexCliBackend(enabled=True, model="gpt-5")
            request = BackendRequest(
                task=TaskName.LINT,
                user_prompt="Return ok=true",
                json_schema_hint='{"type":"object","properties":{"ok":{"type":"boolean"}}}',
            )
            resp = await backend.generate_structured(request)

        assert resp.success is True
        args = mock_exec.await_args.args
        assert "--output-schema" in args

    def test_generate_structured_normalizes_schema_for_codex(self):
        backend = CodexCliBackend(enabled=True, model="gpt-5")
        normalized = json.loads(
            backend._normalized_schema_hint(
                json.dumps(
                    {
                        "type": "object",
                        "properties": {
                            "outer": {
                                "type": "object",
                                "properties": {"ok": {"type": "boolean"}},
                            }
                        },
                    }
                )
            )
        )

        assert normalized["additionalProperties"] is False
        assert normalized["properties"]["outer"]["additionalProperties"] is False


# ---------------------------------------------------------------------------
# Backend Router
# ---------------------------------------------------------------------------


def _make_mock_backend(available: bool = True, response_text: str = "ok") -> ReasoningBackend:
    """Create a mock backend."""
    backend = AsyncMock(spec=ReasoningBackend)
    backend.is_available.return_value = available
    backend.describe.return_value = BackendDescriptor(
        backend_type=BackendType.API,
        available=available,
        reason="" if available else "mock unavailable",
    )
    backend.generate.return_value = BackendResponse(
        text=response_text,
        success=True,
        backend_used=BackendType.API,
        model_used="mock",
    )
    backend.generate_structured.return_value = BackendResponse(
        text=json.dumps({"result": response_text}),
        success=True,
        backend_used=BackendType.API,
        model_used="mock",
    )
    return backend


class TestBackendRouter:
    def test_selects_first_available(self):
        api = _make_mock_backend(available=True)
        oc = _make_mock_backend(available=True)
        router = BackendRouter(
            backends={BackendType.API: api, BackendType.OPENCODE: oc},
            default_order=[BackendType.API, BackendType.OPENCODE],
        )
        selected, reasons = router.select_backend(TaskName.INGEST)
        assert selected is api
        assert len(reasons) == 0

    def test_falls_back_when_first_unavailable(self):
        api = _make_mock_backend(available=False)
        oc = _make_mock_backend(available=True)
        router = BackendRouter(
            backends={BackendType.API: api, BackendType.OPENCODE: oc},
            default_order=[BackendType.API, BackendType.OPENCODE],
        )
        selected, reasons = router.select_backend(TaskName.INGEST)
        assert selected is oc
        assert len(reasons) == 1

    def test_returns_none_when_all_unavailable(self):
        api = _make_mock_backend(available=False)
        oc = _make_mock_backend(available=False)
        router = BackendRouter(
            backends={BackendType.API: api, BackendType.OPENCODE: oc},
            default_order=[BackendType.API, BackendType.OPENCODE],
        )
        selected, reasons = router.select_backend(TaskName.INGEST)
        assert selected is None
        assert len(reasons) == 2

    def test_per_task_order(self):
        api = _make_mock_backend(available=True)
        oc = _make_mock_backend(available=True)
        router = BackendRouter(
            backends={BackendType.API: api, BackendType.OPENCODE: oc},
            task_orders={TaskName.LINT: [BackendType.OPENCODE, BackendType.API]},
            default_order=[BackendType.API, BackendType.OPENCODE],
        )
        selected, _ = router.select_backend(TaskName.LINT)
        assert selected is oc

    @pytest.mark.asyncio
    async def test_generate_uses_first_available(self):
        api = _make_mock_backend(available=True, response_text="from api")
        oc = _make_mock_backend(available=True, response_text="from opencode")
        router = BackendRouter(
            backends={BackendType.API: api, BackendType.OPENCODE: oc},
            default_order=[BackendType.API, BackendType.OPENCODE],
        )
        request = BackendRequest(task=TaskName.QUERY, user_prompt="test")
        resp = await router.generate(request)
        assert resp.success is True
        assert resp.text == "from api"

    @pytest.mark.asyncio
    async def test_generate_falls_back_on_execution_failure(self):
        api = _make_mock_backend(available=True)
        api.generate.return_value = BackendResponse(
            success=False, error="API error", backend_used=BackendType.API
        )
        oc = _make_mock_backend(available=True, response_text="from opencode")
        router = BackendRouter(
            backends={BackendType.API: api, BackendType.OPENCODE: oc},
            default_order=[BackendType.API, BackendType.OPENCODE],
        )
        request = BackendRequest(task=TaskName.QUERY, user_prompt="test")
        resp = await router.generate(request)
        assert resp.success is True
        assert resp.text == "from opencode"
        assert resp.was_fallback is True

    @pytest.mark.asyncio
    async def test_generate_error_when_all_fail(self):
        api = _make_mock_backend(available=True)
        api.generate.return_value = BackendResponse(
            success=False, error="API error", backend_used=BackendType.API
        )
        oc = _make_mock_backend(available=True)
        oc.generate.return_value = BackendResponse(
            success=False, error="OC error", backend_used=BackendType.OPENCODE
        )
        router = BackendRouter(
            backends={BackendType.API: api, BackendType.OPENCODE: oc},
            default_order=[BackendType.API, BackendType.OPENCODE],
        )
        request = BackendRequest(task=TaskName.QUERY, user_prompt="test")
        resp = await router.generate(request)
        assert resp.success is False
        assert "All backends failed" in resp.error

    def test_describe_all(self):
        api = _make_mock_backend(available=True)
        router = BackendRouter(
            backends={BackendType.API: api},
            default_order=[BackendType.API, BackendType.OPENCODE],
        )
        descriptions = router.describe_all(TaskName.INGEST)
        assert len(descriptions) == 2
        assert descriptions[1].available is False
        assert descriptions[1].reason == "not registered"


class TestBackendOrderParsing:
    def test_ignores_unknown_tokens_when_not_strict(self, caplog):
        order = _parse_order(
            "api,unknown,claude",
            known_backend_ids={"api", "opencode", "claude_code", "codex"},
            strict=False,
        )

        assert order == ["api", "claude_code"]
        assert "Unknown backend token 'unknown'" in caplog.text

    def test_raises_on_unknown_tokens_in_strict_mode(self):
        with pytest.raises(ValueError):
            _parse_order(
                "api,unknown",
                known_backend_ids={"api", "opencode", "claude_code", "codex"},
                strict=True,
            )
