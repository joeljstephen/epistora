"""Tests for Phase 4 plugin manifest and loading foundation."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.backends.base import ReasoningBackend
from app.backends.models import BackendRequest, TaskName
from app.compiler.prompts import get_source_analysis_prompt
from app.config import Settings
from app.connectors.registry import build_inbox_connectors
from app.plugins.loader import discover_plugins
from app.plugins.manifest import PluginManifest
from app.sinks.registry import build_default_sink, build_sink


def test_plugin_manifest_validation_requires_expected_entrypoint(tmp_path: Path):
    plugin_dir = tmp_path / "bad_sink"
    plugin_dir.mkdir()
    (plugin_dir / "epistora-plugin.toml").write_text(
        """
[plugin]
id = "bad_sink"
name = "Bad Sink"
version = "0.1.0"
type = "sink"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="entrypoints.factory"):
        PluginManifest.from_toml(plugin_dir / "epistora-plugin.toml")


def test_plugin_registry_discovers_and_loads_sink_plugin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    plugin_root = tmp_path / "plugins"
    plugin_dir = plugin_root / "example_sink"
    plugin_dir.mkdir(parents=True)

    _write_module(
        tmp_path / "example_plugin.py",
        """
class ExampleSink:
    sink_id = "example_sink"

    def __init__(self, vault_path):
        self.vault_path = vault_path

    def publish(self, *, content, bundle):
        return []


def build_sink(settings):
    return ExampleSink(settings.vault_path)
""".strip(),
    )
    _write_manifest(
        plugin_dir / "epistora-plugin.toml",
        """
[plugin]
id = "example_sink"
name = "Example Sink"
version = "0.1.0"
type = "sink"

[compatibility]
min_epistora_version = "0.1.0"
max_epistora_version = "0.9.0"

[entrypoints]
factory = "example_plugin:build_sink"

[config_schema]
type = "object"
required = ["enabled"]
additionalProperties = false

[config_schema.properties.enabled]
type = "boolean"
""".strip(),
    )

    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("EPISTORA_PLUGIN_DIRS", str(plugin_root))

    registry = discover_plugins(strict=True)
    assert registry.get("example_sink").manifest.plugin_type == "sink"
    assert registry.validate_config("example_sink", {"enabled": True}) == {"enabled": True}

    with pytest.raises(ValueError, match="missing required key 'enabled'"):
        registry.validate_config("example_sink", {})

    settings = Settings(vault_path=tmp_path / "vault")
    sink = build_sink("example_sink", settings)
    assert sink.sink_id == "example_sink"
    assert build_default_sink(settings).sink_id == "markdown_vault"


def test_plugin_compatibility_checks():
    manifest = PluginManifest.model_validate(
        {
            "id": "legacy_backend",
            "name": "Legacy Backend",
            "version": "0.1.0",
            "type": "reasoning_backend",
            "compatibility": {
                "min_epistora_version": "0.0.1",
                "max_epistora_version": "0.0.9",
            },
            "entrypoints": {"factory": "legacy_plugin:build_backend"},
        }
    )

    assert manifest.is_compatible("0.0.5") is True
    assert manifest.is_compatible("0.1.0") is False


def test_prompt_pack_plugin_overrides_prompt_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    plugin_root = tmp_path / "plugins"
    plugin_dir = plugin_root / "research_pack"
    prompts_dir = plugin_dir / "prompts" / "ingest"
    prompts_dir.mkdir(parents=True)

    _write_manifest(
        plugin_dir / "epistora-plugin.toml",
        """
[plugin]
id = "research_pack"
name = "Research Pack"
version = "0.1.0"
type = "prompt_pack"

[compatibility]
min_epistora_version = "0.1.0"

[entrypoints]
prompt_pack_dir = "prompts"
""".strip(),
    )
    (prompts_dir / "source_analysis.md").write_text(
        "Plugin prompt content",
        encoding="utf-8",
    )

    monkeypatch.setenv("EPISTORA_PLUGIN_DIRS", str(plugin_root))
    monkeypatch.setenv("EPISTORA_PROMPT_PACK", "research_pack")

    assert get_source_analysis_prompt() == "Plugin prompt content"


def test_build_inbox_connectors_includes_plugin_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    plugin_root = tmp_path / "plugins"
    plugin_dir = plugin_root / "example_inbox"
    plugin_dir.mkdir(parents=True)

    _write_module(
        tmp_path / "example_inbox_plugin.py",
        """
from datetime import datetime


class ExampleConnector:
    connector_id = "example_inbox"

    def fetch_since(self, since: datetime, limit: int = 100):
        return []


def build_connector(settings):
    return ExampleConnector()
""".strip(),
    )
    _write_manifest(
        plugin_dir / "epistora-plugin.toml",
        """
[plugin]
id = "example_inbox"
name = "Example Inbox"
version = "0.1.0"
type = "inbox_provider"

[compatibility]
min_epistora_version = "0.1.0"

[entrypoints]
factory = "example_inbox_plugin:build_connector"
""".strip(),
    )

    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("EPISTORA_PLUGIN_DIRS", str(plugin_root))

    connectors = build_inbox_connectors(Settings())
    assert "example_inbox" in connectors


@pytest.mark.asyncio
async def test_build_backends_includes_plugin_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.backends.registry import build_backends

    plugin_root = tmp_path / "plugins"
    plugin_dir = plugin_root / "example_backend"
    plugin_dir.mkdir(parents=True)

    _write_module(
        tmp_path / "example_backend_plugin.py",
        """
from app.backends.base import ReasoningBackend
from app.backends.models import BackendDescriptor, BackendResponse, TaskName


class ExampleBackend(ReasoningBackend):
    def is_available(self, task: TaskName | None = None) -> bool:
        return True

    def describe(self, task: TaskName | None = None) -> BackendDescriptor:
        return BackendDescriptor(
            backend_type="example_backend",
            available=True,
            model="plugin-model",
        )

    async def generate(self, request):
        return BackendResponse(success=True, text="plugin", backend_used="example_backend")


def build_backend(settings):
    return ExampleBackend()
""".strip(),
    )
    _write_manifest(
        plugin_dir / "epistora-plugin.toml",
        """
[plugin]
id = "example_backend"
name = "Example Backend"
version = "0.1.0"
type = "reasoning_backend"

[compatibility]
min_epistora_version = "0.1.0"

[entrypoints]
factory = "example_backend_plugin:build_backend"
""".strip(),
    )

    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("EPISTORA_PLUGIN_DIRS", str(plugin_root))

    backends = build_backends(Settings())
    backend = backends["example_backend"]
    assert isinstance(backend, ReasoningBackend)
    assert backend.describe(TaskName.INGEST).backend_type == "example_backend"
    response = await backend.generate(
        BackendRequest(
            task=TaskName.INGEST,
            system_prompt="system",
            user_prompt="user",
        )
    )
    assert response.success is True


def test_plugin_manifest_accepts_maintenance_and_retrieval_types(tmp_path: Path):
    """Verify that maintenance_plugin and retrieval_provider are accepted plugin types."""
    for plugin_type in ("maintenance_plugin", "retrieval_provider"):
        plugin_dir = tmp_path / plugin_type
        plugin_dir.mkdir(parents=True, exist_ok=True)
        _write_manifest(
            plugin_dir / "epistora-plugin.toml",
            f"""
[plugin]
id = "test_{plugin_type}"
name = "Test {plugin_type}"
version = "0.1.0"
type = "{plugin_type}"

[entrypoints]
factory = "test_module:build"
""".strip(),
        )
        manifest = PluginManifest.from_toml(plugin_dir / "epistora-plugin.toml")
        assert manifest.plugin_type == plugin_type


def test_plugin_manifest_rejects_unsupported_type(tmp_path: Path):
    """Verify that unsupported plugin types are rejected."""
    plugin_dir = tmp_path / "bad_type"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    _write_manifest(
        plugin_dir / "epistora-plugin.toml",
        """
[plugin]
id = "bad_type"
name = "Bad Type"
version = "0.1.0"
type = "not_a_real_type"

[entrypoints]
factory = "test_module:build"
""".strip(),
    )
    with pytest.raises(ValueError, match="Unsupported plugin type"):
        PluginManifest.from_toml(plugin_dir / "epistora-plugin.toml")


def _write_manifest(path: Path, content: str) -> None:
    path.write_text(content + "\n", encoding="utf-8")


def _write_module(path: Path, content: str) -> None:
    path.write_text(content + "\n", encoding="utf-8")
