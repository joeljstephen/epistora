# Canonical Artifact Layer

This document describes the Phase 1 v2 refactor that introduces canonical internal artifacts without changing the current vault structure or public CLI/API behavior.

## Why This Exists

The v2 architecture spec makes a specific shift:

- evidence extraction should produce evidence-layer objects
- the compiler should produce canonical knowledge artifacts
- rendering should consume those artifacts instead of building markdown directly from ad hoc intermediate objects

Epistora still renders the same markdown vault in Phase 1, but it no longer needs to think of markdown notes as the first internal representation after ingest analysis.

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
   - `app/vault/writer.py`
   - current markdown vault output is rendered from canonical artifacts

In short:

```text
SourceItem -> SourceContent -> ArtifactBundle -> VaultWriter -> markdown vault
```

## Canonical Models Added In Phase 1

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

- before Phase 1:
  - created legacy `Topic`, `Entity`, and `Concept` models directly
- after Phase 1:
  - creates a canonical `ArtifactBundle`
  - normalizes bullet-heavy analysis fields into structured artifact fields
  - creates `RelationshipArtifact` edges from source to topics/entities/concepts
  - creates `EvidenceReference` records tied to the extracted source evidence

The `write_vault` stage now renders from that artifact bundle.

## Compatibility Strategy

Phase 1 intentionally does not add the full sink system yet.

To preserve current behavior:

- `VaultWriter.write_artifact_bundle(...)` is the new production rendering entrypoint
- existing markdown templates remain in place
- compatibility adapters in `app/artifacts/compat.py` translate canonical artifacts into the current markdown-oriented writer/template inputs
- existing public CLI/API behavior and visible vault structure remain unchanged

This keeps the new layer real while avoiding a large sink refactor before Phase 2.

## Safe Automation Path

The queue automation safe mode also now builds an `ArtifactBundle` before writing output.

That matters because Phase 1 is not only about the main ingest graph. The current production write paths should consume the canonical layer instead of bypassing it whenever they are compiling source understanding into durable vault notes.

## Intentionally Not Done In Phase 1

This phase does not introduce:

- sink interfaces or multiple sinks
- retrieval redesign
- plugin manifests or plugin loading
- a richer read model
- a new visible vault layout

Those remain later v2 phases.

## Next Architectural Step

Phase 2 can now refactor the current vault writer into an explicit markdown sink without first needing to invent a canonical model. The compiler/output boundary already exists.
