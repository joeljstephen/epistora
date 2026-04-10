"""Plugin manifest and discovery helpers."""

from app.plugins.loader import (
    PLUGIN_DIRS_ENV_VAR,
    PROMPT_PACK_ENV_VAR,
    PluginRegistry,
    active_prompt_pack_root,
    discover_plugins,
    plugin_factories,
    plugin_search_paths,
)
from app.plugins.manifest import CORE_VERSION, PluginCompatibility, PluginManifest

__all__ = [
    "CORE_VERSION",
    "PLUGIN_DIRS_ENV_VAR",
    "PROMPT_PACK_ENV_VAR",
    "PluginCompatibility",
    "PluginManifest",
    "PluginRegistry",
    "active_prompt_pack_root",
    "discover_plugins",
    "plugin_factories",
    "plugin_search_paths",
]
