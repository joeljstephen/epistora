# Markdown Vault Sink

This document describes the default markdown vault sink. The compiler produces
canonical artifacts first; the sink owns markdown-vault publishing.

## What Changed

The relevant boundary is now:

```text
SourceContent -> ArtifactBundle -> ArtifactSink -> rendered outputs
```

The default sink is:

- [`MarkdownVaultSink`](/Users/joeljacobstephen/Code/projects/epistora/app/sinks/markdown_vault.py)

The sink contract lives in:

- [`app/sinks/base.py`](/Users/joeljacobstephen/Code/projects/epistora/app/sinks/base.py)

The default sink construction lives in:

- [`app/sinks/registry.py`](/Users/joeljacobstephen/Code/projects/epistora/app/sinks/registry.py)

## Ownership

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

It is now one sink behind a sink boundary. JSON export can also be enabled as a
second sink.

## Compatibility

Current vault behavior and layout are preserved:

- `raw/`
- `wiki/`
- `outputs/`
- existing note templates
- current merge/update behavior for hub pages

[`VaultWriter`](/Users/joeljacobstephen/Code/projects/epistora/app/vault/writer.py) remains as a thin compatibility wrapper around `MarkdownVaultSink` for tests and helper code that still import it directly.

## Current Responsibilities

The markdown sink also triggers the current vault-side derived work after
publishing:

- rebuilds `wiki/indexes/` pages, including reader views
- writes the Obsidian reader-view CSS snippet
- refreshes the read model for changed paths where possible

## Current Boundary

The markdown sink still renders through the existing templates and compatibility
adapters. Direct artifact-to-markdown rendering is a future cleanup, not a
current requirement.
