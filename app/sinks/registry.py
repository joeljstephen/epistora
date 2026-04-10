"""Sink registry and default sink construction."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.config import Settings, get_settings
from app.plugins.loader import plugin_factories
from app.sinks.base import ArtifactSink
from app.sinks.composite import CompositeSink
from app.sinks.json_export import JsonExportSink
from app.sinks.markdown_vault import MarkdownVaultSink
from app.storage.evidence import evidence_storage_policy_from_settings

SinkFactory = Callable[[Settings], ArtifactSink]


def _builtin_sink_factories() -> dict[str, SinkFactory]:
    return {
        "json_export": lambda settings: JsonExportSink(
            settings.vault_path,
            _resolve_json_export_root(settings),
        ),
        "markdown_vault": lambda settings: MarkdownVaultSink(
            settings.vault_path,
            storage_policy=evidence_storage_policy_from_settings(settings),
        ),
    }


def _resolve_json_export_root(settings: Settings) -> Path:
    configured = Path(settings.json_export_dir).expanduser()
    if configured.is_absolute():
        return configured.resolve()
    return (settings.vault_path / configured).resolve()


def _configured_sink_ids(settings: Settings) -> list[str]:
    configured = getattr(settings, "artifact_sink_ids", "markdown_vault")
    if not isinstance(configured, str):
        return ["markdown_vault"]

    sink_ids: list[str] = []
    for sink_id in configured.split(","):
        normalized = sink_id.strip()
        if not normalized or normalized in sink_ids:
            continue
        sink_ids.append(normalized)
    return sink_ids or ["markdown_vault"]


def available_sink_ids(settings: Settings | None = None) -> list[str]:
    resolved_settings = settings or get_settings()
    factories = _builtin_sink_factories()
    factories.update(plugin_factories("sink", resolved_settings))
    return sorted(factories)


def build_sink(sink_id: str, settings: Settings | None = None) -> ArtifactSink:
    resolved_settings = settings or get_settings()
    factories = _builtin_sink_factories()
    factories.update(plugin_factories("sink", resolved_settings))
    factory = factories.get(sink_id)
    if factory is None:
        available = ", ".join(sorted(factories))
        raise ValueError(f"Unknown sink '{sink_id}'. Available sinks: {available}")
    return factory(resolved_settings)


def build_default_sink(settings: Settings | None = None) -> ArtifactSink:
    resolved_settings = settings or get_settings()
    sink_ids = _configured_sink_ids(resolved_settings)
    sinks = [build_sink(sink_id, resolved_settings) for sink_id in sink_ids]
    if len(sinks) == 1:
        return sinks[0]
    return CompositeSink(sinks)
