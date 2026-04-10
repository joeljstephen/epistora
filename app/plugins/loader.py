"""Discovery and runtime loading for local plugin manifests."""

from __future__ import annotations

import importlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import Settings, epistora_home, project_root
from app.plugins.manifest import CORE_VERSION, PluginManifest, ensure_manifest_valid

logger = logging.getLogger(__name__)

PLUGIN_DIRS_ENV_VAR = "EPISTORA_PLUGIN_DIRS"
PROMPT_PACK_ENV_VAR = "EPISTORA_PROMPT_PACK"
PLUGIN_MANIFEST_NAMES = ("epistora-plugin.toml", "plugin.toml")


@dataclass(frozen=True)
class DiscoveredPlugin:
    """A plugin manifest discovered on disk."""

    manifest: PluginManifest
    root_path: Path
    manifest_path: Path

    @property
    def plugin_id(self) -> str:
        return self.manifest.plugin_id

    def prompt_pack_path(self) -> Path:
        """Return the plugin's prompt-pack directory."""
        relative = self.manifest.entrypoints.prompt_pack_dir
        return (self.root_path / relative).resolve()


class PluginRegistry:
    """In-memory view of discovered plugins."""

    def __init__(
        self,
        plugins: dict[str, DiscoveredPlugin],
        *,
        current_version: str = CORE_VERSION,
        errors: list[str] | None = None,
    ) -> None:
        self._plugins = plugins
        self._current_version = current_version
        self.errors = errors or []

    def all(self, plugin_type: str | None = None) -> list[DiscoveredPlugin]:
        """Return all discovered plugins, optionally filtered by type."""
        plugins = list(self._plugins.values())
        if plugin_type is None:
            return sorted(plugins, key=lambda plugin: plugin.plugin_id)
        return sorted(
            (plugin for plugin in plugins if plugin.manifest.plugin_type == plugin_type),
            key=lambda plugin: plugin.plugin_id,
        )

    def compatible(self, plugin_type: str | None = None) -> list[DiscoveredPlugin]:
        """Return compatible plugins, optionally filtered by type."""
        return [
            plugin
            for plugin in self.all(plugin_type)
            if plugin.manifest.is_compatible(self._current_version)
        ]

    def get(self, plugin_id: str) -> DiscoveredPlugin:
        """Return a discovered plugin by ID."""
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            raise KeyError(f"Plugin '{plugin_id}' was not discovered")
        return plugin

    def load_factory(self, plugin_id: str) -> Any:
        """Import and return a plugin's factory entrypoint."""
        plugin = self.get(plugin_id)
        manifest = plugin.manifest
        if not manifest.is_compatible(self._current_version):
            raise ValueError(
                f"Plugin '{plugin_id}' is not compatible with Epistora {self._current_version}"
            )
        if not manifest.entrypoints.factory:
            raise ValueError(f"Plugin '{plugin_id}' does not declare a factory entrypoint")

        module_name, _, attr_name = manifest.entrypoints.factory.partition(":")
        if not module_name or not attr_name:
            raise ValueError(
                f"Plugin '{plugin_id}' has invalid factory entrypoint "
                f"'{manifest.entrypoints.factory}'"
            )
        module = importlib.import_module(module_name)
        factory = getattr(module, attr_name, None)
        if factory is None:
            raise ValueError(
                f"Plugin '{plugin_id}' entrypoint '{manifest.entrypoints.factory}' was not found"
            )
        return factory

    def prompt_pack_root(self, plugin_id: str) -> Path:
        """Resolve a prompt pack root by plugin ID."""
        plugin = self.get(plugin_id)
        manifest = plugin.manifest
        if manifest.plugin_type != "prompt_pack":
            raise ValueError(f"Plugin '{plugin_id}' is not a prompt_pack plugin")
        if not manifest.is_compatible(self._current_version):
            raise ValueError(
                f"Plugin '{plugin_id}' is not compatible with Epistora {self._current_version}"
            )
        prompt_root = plugin.prompt_pack_path()
        if not prompt_root.exists():
            raise ValueError(
                f"Prompt pack directory '{prompt_root}' does not exist for plugin '{plugin_id}'"
            )
        return prompt_root

    def validate_config(self, plugin_id: str, config: dict[str, Any]) -> dict[str, Any]:
        """Validate config for a discovered plugin."""
        return self.get(plugin_id).manifest.validate_config(config)


def discover_plugins(
    settings: Settings | None = None,
    *,
    strict: bool = False,
) -> PluginRegistry:
    """Discover local plugins from the configured search paths."""
    _ = settings
    plugins: dict[str, DiscoveredPlugin] = {}
    errors: list[str] = []

    for root in plugin_search_paths():
        if not root.exists():
            continue
        for manifest_path in _manifest_paths(root):
            try:
                manifest = ensure_manifest_valid(manifest_path)
            except ValueError as exc:
                if strict:
                    raise
                logger.warning("%s", exc)
                errors.append(str(exc))
                continue

            plugin = DiscoveredPlugin(
                manifest=manifest,
                root_path=manifest_path.parent,
                manifest_path=manifest_path,
            )
            if plugin.plugin_id in plugins:
                message = (
                    f"Duplicate plugin id '{plugin.plugin_id}' discovered at {manifest_path}"
                )
                if strict:
                    raise ValueError(message)
                logger.warning("%s", message)
                errors.append(message)
                continue
            plugins[plugin.plugin_id] = plugin

    return PluginRegistry(plugins, errors=errors)


def plugin_search_paths() -> tuple[Path, ...]:
    """Return plugin directories searched by the loader."""
    roots: list[Path] = []

    override = os.environ.get(PLUGIN_DIRS_ENV_VAR, "").strip()
    if override:
        for part in override.split(os.pathsep):
            if part.strip():
                roots.append(Path(part).expanduser().resolve())

    roots.append((project_root() / "plugins").resolve())
    roots.append((epistora_home() / "plugins").resolve())

    unique: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if root not in seen:
            seen.add(root)
            unique.append(root)
    return tuple(unique)


def plugin_factories(plugin_type: str, settings: Settings | None = None) -> dict[str, Any]:
    """Load compatible plugin factories for a category."""
    registry = discover_plugins(settings)
    factories: dict[str, Any] = {}
    for plugin in registry.compatible(plugin_type):
        manifest = plugin.manifest
        if not manifest.entrypoints.factory:
            continue
        try:
            factories[plugin.plugin_id] = registry.load_factory(plugin.plugin_id)
        except Exception as exc:  # pragma: no cover - defensive isolation
            logger.warning(
                "Failed to load %s plugin '%s': %s",
                plugin_type,
                plugin.plugin_id,
                exc,
            )
    return factories


def active_prompt_pack_root(settings: Settings | None = None) -> Path | None:
    """Return the selected prompt-pack plugin root if one is configured."""
    _ = settings
    plugin_id = os.environ.get(PROMPT_PACK_ENV_VAR, "").strip()
    if not plugin_id:
        return None
    return discover_plugins().prompt_pack_root(plugin_id)


def _manifest_paths(root: Path) -> list[Path]:
    manifests: list[Path] = []
    for candidate in PLUGIN_MANIFEST_NAMES:
        if (root / candidate).exists():
            manifests.append((root / candidate).resolve())

    for child in sorted(path for path in root.iterdir() if path.is_dir()):
        for candidate in PLUGIN_MANIFEST_NAMES:
            manifest_path = child / candidate
            if manifest_path.exists():
                manifests.append(manifest_path.resolve())
                break

    return manifests
