# Markdown Vault Sink

This document describes the Phase 2 refactor that turns markdown vault output into a sink implementation instead of treating the vault writer as the compiler's native output model.

## What Changed

The relevant boundary is now:

```text
SourceContent -> ArtifactBundle -> ArtifactSink -> rendered outputs
```

For Phase 2, there is only one sink:

- [`MarkdownVaultSink`](/Users/joeljacobstephen/Code/projects/epistora/app/sinks/markdown_vault.py)

The sink contract lives in:

- [`app/sinks/base.py`](/Users/joeljacobstephen/Code/projects/epistora/app/sinks/base.py)

The default sink construction lives in:

- [`app/sinks/registry.py`](/Users/joeljacobstephen/Code/projects/epistora/app/sinks/registry.py)

## Ownership After Phase 2

### Compiler

The compiler owns:

- evidence normalization
- source analysis
- canonical artifact creation

The compiler no longer owns markdown publishing details.

### Sink

The markdown sink owns:

- raw capture rendering
- source/topic/entity/concept/synthesis note rendering
- markdown-vault-specific structure preparation
- markdown index rebuilding

This is intentionally still the only sink in Phase 2, but it is now behind a sink boundary.

## Compatibility

Current vault behavior and layout are preserved:

- `raw/`
- `wiki/`
- `outputs/`
- existing note templates
- current merge/update behavior for hub pages

[`VaultWriter`](/Users/joeljacobstephen/Code/projects/epistora/app/vault/writer.py) remains as a thin compatibility wrapper around `MarkdownVaultSink` for tests and helper code that still import it directly.

## Why This Matters

Phase 1 introduced canonical artifacts.

Phase 2 makes those artifacts publish through a sink contract instead of being rendered by compiler-aware vault-writing code. That is the architectural step needed before adding:

- a second sink
- plugin-owned sinks
- cleaner compiler publish contracts

## Intentionally Not Done

Phase 2 does not add:

- a second sink
- sink plugins
- storage tier redesign
- read-model redesign
- prompt/plugin manifest work

Those stay in later phases.
