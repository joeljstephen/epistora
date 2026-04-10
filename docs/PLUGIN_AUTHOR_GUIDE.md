# Plugin Author Guide

Phase 4 introduces Epistora's first manifest-based plugin foundation. The goal is to make extension a stable product surface without converting every internal subsystem into plugins immediately.

## What Exists In Phase 4

The plugin foundation lives under:

- [`app/plugins/manifest.py`](/Users/joeljacobstephen/Code/projects/epistora/app/plugins/manifest.py)
- [`app/plugins/loader.py`](/Users/joeljacobstephen/Code/projects/epistora/app/plugins/loader.py)

Current runtime integration points:

- inbox providers via [`app/connectors/registry.py`](/Users/joeljacobstephen/Code/projects/epistora/app/connectors/registry.py)
- reasoning backends via [`app/backends/registry.py`](/Users/joeljacobstephen/Code/projects/epistora/app/backends/registry.py)
- sinks via [`app/sinks/registry.py`](/Users/joeljacobstephen/Code/projects/epistora/app/sinks/registry.py)
- prompt packs via [`app/compiler/prompts.py`](/Users/joeljacobstephen/Code/projects/epistora/app/compiler/prompts.py)

Extractor manifests are supported in the model and loader, but the extraction pipeline is not yet registry-driven. That is an intentional Phase 4 boundary.

## Plugin Search Paths

Epistora discovers local plugins from:

- `plugins/` under the repo root
- `plugins/` under `EPISTORA_HOME`
- any directories listed in `EPISTORA_PLUGIN_DIRS`

`EPISTORA_PLUGIN_DIRS` uses the OS path separator:

- macOS/Linux: `:`
- Windows: `;`

Each plugin lives in its own directory and should contain either:

- `epistora-plugin.toml`
- `plugin.toml`

For local development, the simplest workflow is:

1. Create a plugin under `plugins/<plugin_id>/`
2. Point Epistora at it with `EPISTORA_PLUGIN_DIRS` if needed
3. Run `epistora doctor` to verify plugin discovery and prompt-pack health
4. Run `uv run pytest tests/test_plugins.py`

## Supported Plugin Types

Phase 4 manifest support includes:

- `inbox_provider`
- `extractor`
- `reasoning_backend`
- `prompt_pack`
- `sink`

## Manifest Format

Example sink plugin:

```toml
[plugin]
id = "example_sink"
name = "Example Sink"
version = "0.1.0"
type = "sink"
description = "Small example sink plugin"
capabilities = ["exports-demo-output"]

[compatibility]
min_epistora_version = "0.1.0"
max_epistora_version = "0.9.0"

[entrypoints]
factory = "example_plugin:build_sink"

[config_schema]
type = "object"
required = ["enabled"]

[config_schema.properties.enabled]
type = "boolean"
```

Example prompt-pack plugin:

```toml
[plugin]
id = "research_pack"
name = "Research Prompt Pack"
version = "0.1.0"
type = "prompt_pack"

[compatibility]
min_epistora_version = "0.1.0"

[entrypoints]
prompt_pack_dir = "prompts"
```

## Entrypoint Rules

Non-prompt-pack plugins should declare:

- `entrypoints.factory = "python_module:callable_name"`

That callable should return the runtime object for the category when given `Settings`.

Examples:

- inbox provider factory returns a `LinkInboxConnector`
- reasoning backend factory returns a `ReasoningBackend`
- sink factory returns an `ArtifactSink`

Prompt-pack plugins declare:

- `entrypoints.prompt_pack_dir = "relative/path/inside/plugin"`

To activate a prompt pack, set `EPISTORA_PROMPT_PACK=<plugin_id>`.

You can confirm the active prompt pack and plugin discovery state with:

```bash
epistora doctor
```

## Compatibility And Config

Phase 4 supports:

- plugin version
- Epistora compatibility range
- a lightweight object-shaped config schema

Config-schema validation currently supports:

- `required`
- `properties`
- basic property types: `string`, `integer`, `number`, `boolean`, `object`, `array`
- optional `additionalProperties = false`

This is intentionally smaller than a full marketplace/package-management system.

## Current Boundaries

Core still owns:

- canonical artifact models
- compiler flow
- markdown vault as the default sink
- queue automation
- read model

Plugins can now extend the runtime without editing those core modules, but Phase 4 does not yet add:

- remote plugin install/distribution
- a marketplace
- full extractor plugin execution
- prompt composition redesign

That means the current extension story is intentionally local-first and repo-friendly, not a hosted plugin ecosystem.
