# Canonical Artifact Layer

This document describes Epistora's canonical internal artifact layer. It is the
compiler boundary between normalized evidence and any configured output sink.

## Why This Exists

The current architecture makes a specific shift:

- evidence extraction should produce evidence-layer objects
- the compiler should produce canonical knowledge artifacts
- rendering should consume those artifacts instead of building markdown directly from ad hoc intermediate objects

Epistora still renders a markdown vault by default, but markdown notes are no
longer the first internal representation after ingest analysis.

## Current Pipeline Boundary

The pipeline now has three explicit layers:

1. Evidence layer
   - `app/models/source.py`
   - `SourceItem` and `SourceContent`
   - fetchers and extractors stop here
2. Canonical artifact layer
   - `app/artifacts/models.py`
   - `app/artifacts/builder.py`
   - compiler analysis is normalized into `ArtifactBundle`
3. Rendered output layer
   - `app/sinks/`
   - markdown vault and optional JSON output are rendered from canonical artifacts

In short:

```text
SourceItem -> SourceContent -> ArtifactBundle -> configured sinks
```

## Canonical Models

The canonical package now defines:

- `SourceArtifact`
- `TopicArtifact`
- `EntityArtifact`
- `ConceptArtifact`
- `RelationshipArtifact`
- `SynthesisArtifact`
- `EvidenceReference`
- `ArtifactBundle`

`ArtifactBundle` is the compiler output boundary. It keeps the source artifact plus related hub artifacts, relationships, and evidence references together before rendering.

## What The Compiler Now Does

`app/compiler/ingest_graph.py` still performs the same high-level steps:

```text
fetch -> dedup -> analyse -> extract_knowledge -> write_vault -> persist
```

The important internal change is the `extract_knowledge` stage:

- earlier implementation:
  - created legacy `Topic`, `Entity`, and `Concept` models directly
- current implementation:
  - creates a canonical `ArtifactBundle`
  - normalizes bullet-heavy analysis fields into structured artifact fields
  - creates `RelationshipArtifact` edges from source to topics/entities/concepts
  - creates `EvidenceReference` records tied to the extracted source evidence

The `write_vault` stage now renders from that artifact bundle.

## Current Rendering Strategy

Configured sinks consume `ArtifactBundle`s through the sink boundary:

- `MarkdownVaultSink` remains the default human-facing sink.
- `JsonExportSink` can be enabled for deterministic machine-facing exports.
- `VaultWriter` remains as a compatibility wrapper around the markdown sink.
- `app/artifacts/compat.py` still translates canonical artifacts into the
  current markdown template inputs.

## Safe Automation Path

The queue automation safe mode also now builds an `ArtifactBundle` before writing output.

That matters because the canonical layer is not only about the main ingest
graph. Current production write paths should consume this boundary instead of
bypassing it whenever they compile source understanding into durable vault
notes.

## Current Boundaries

This layer still does not introduce:

- a richer read model
- a new visible vault layout
- direct artifact-to-markdown rendering without the compatibility adapter

The compiler/output boundary is stable enough for current personal-learning,
query, maintenance, and export workflows.
