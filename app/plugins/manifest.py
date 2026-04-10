"""Plugin manifest models and validation helpers."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, model_validator

CORE_VERSION = "0.1.0"
_VERSION_RE = re.compile(r"^\d+(?:\.\d+)*(?:[-+][A-Za-z0-9_.-]+)?$")


class PluginCompatibility(BaseModel):
    """Compatibility range for an Epistora plugin."""

    min_epistora_version: str = ""
    max_epistora_version: str = ""

    def is_compatible(self, current_version: str = CORE_VERSION) -> bool:
        """Return whether *current_version* falls within this compatibility range."""
        current = _parse_version(current_version)
        if self.min_epistora_version and current < _parse_version(self.min_epistora_version):
            return False
        if self.max_epistora_version and current > _parse_version(self.max_epistora_version):
            return False
        return True


class PluginEntrypoints(BaseModel):
    """Entrypoints declared by a plugin manifest."""

    factory: str = ""
    prompt_pack_dir: str = ""


class PluginManifest(BaseModel):
    """Manifest for a local Epistora plugin."""

    plugin_id: str = Field(alias="id", pattern=r"^[a-z0-9][a-z0-9._-]*$")
    name: str
    version: str
    plugin_type: str = Field(alias="type")
    description: str = ""
    compatibility: PluginCompatibility = Field(default_factory=PluginCompatibility)
    config_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object"})
    capabilities: list[str] = Field(default_factory=list)
    entrypoints: PluginEntrypoints = Field(default_factory=PluginEntrypoints)
    install_requirements: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_manifest(self) -> PluginManifest:
        if not _VERSION_RE.match(self.version):
            raise ValueError(f"Invalid plugin version '{self.version}'")
        supported = {
            "inbox_provider",
            "extractor",
            "reasoning_backend",
            "prompt_pack",
            "sink",
            "maintenance_plugin",
            "retrieval_provider",
        }
        if self.plugin_type not in supported:
            raise ValueError(f"Unsupported plugin type '{self.plugin_type}'")
        if self.plugin_type == "prompt_pack":
            if not self.entrypoints.prompt_pack_dir:
                raise ValueError("Prompt pack plugins must declare entrypoints.prompt_pack_dir")
        elif not self.entrypoints.factory:
            raise ValueError(
                f"{self.plugin_type} plugins must declare entrypoints.factory"
            )
        return self

    @classmethod
    def from_toml(cls, manifest_path: Path) -> PluginManifest:
        """Parse and validate a plugin manifest file."""
        data = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
        plugin_data = data.get("plugin", data)
        plugin_data = dict(plugin_data)
        plugin_data["compatibility"] = data.get(
            "compatibility",
            plugin_data.get("compatibility", {}),
        )
        plugin_data["entrypoints"] = data.get(
            "entrypoints",
            plugin_data.get("entrypoints", {}),
        )
        plugin_data["config_schema"] = data.get(
            "config_schema",
            plugin_data.get("config_schema", {"type": "object"}),
        )
        return cls.model_validate(plugin_data)

    def is_compatible(self, current_version: str = CORE_VERSION) -> bool:
        """Return whether this plugin is compatible with the current core version."""
        return self.compatibility.is_compatible(current_version)

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Validate plugin config against the manifest's lightweight schema."""
        schema = self.config_schema or {"type": "object"}
        if schema.get("type", "object") != "object":
            raise ValueError("Only object config schemas are supported in Phase 4")

        required = schema.get("required", [])
        properties = schema.get("properties", {})
        additional_allowed = schema.get("additionalProperties", True)

        for key in required:
            if key not in config:
                raise ValueError(
                    f"Plugin '{self.plugin_id}' config missing required key '{key}'"
                )

        for key, value in config.items():
            prop_schema = properties.get(key)
            if prop_schema is None:
                if additional_allowed is False:
                    raise ValueError(
                        f"Plugin '{self.plugin_id}' config contains unsupported key '{key}'"
                    )
                continue
            _validate_json_value(key, value, prop_schema)

        return config


def _parse_version(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for raw_part in version.split("."):
        match = re.match(r"^(\d+)", raw_part)
        parts.append(int(match.group(1)) if match else 0)
    return tuple(parts)


def _validate_json_value(key: str, value: Any, schema: dict[str, Any]) -> None:
    expected = schema.get("type", "")
    type_ok = {
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
    }.get(expected, True)

    if not type_ok:
        raise ValueError(
            f"Plugin config key '{key}' expected type '{expected}', got '{type(value).__name__}'"
        )


def ensure_manifest_valid(manifest_path: Path) -> PluginManifest:
    """Load a manifest and normalize validation errors."""
    try:
        return PluginManifest.from_toml(manifest_path)
    except ValidationError as exc:
        raise ValueError(f"Invalid plugin manifest at {manifest_path}: {exc}") from exc
