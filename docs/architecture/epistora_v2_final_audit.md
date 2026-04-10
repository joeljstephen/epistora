# Epistora v2 Final Audit

**Date:** 2026-04-09  
**Spec:** `docs/epistora_v_2_architecture_spec.md`  
**Audit scope:** full repository review, test/lint execution, live ingest smoke test, local automation verification

## 1. Overall Status Summary

Epistora is now a credible **v2 foundation**, but not every part of the v2 spec is equally complete.

The important architectural shift is real:

- the compiler now produces canonical artifacts before rendering
- sinks are explicit and pluggable
- the markdown vault is no longer the only internal representation
- prompt composition, storage tiering, queue-based automation, and a derived read model all exist

The main caveat is that several areas are still **foundation-level implementations rather than full v2 realizations**:

- the read model exists, but retrieval is not consistently centered on it
- maintenance exists, but remains bounded and fairly lightweight
- deep automation is better than v1, but balanced and deep still share the same ingest graph path
- plugin support exists, but the public plugin surface is still thin

**Readiness judgment:** the codebase is ready to be treated as the **v2 foundation**, but not as a finished or exhaustive implementation of the entire v2 architecture spec.

## 2. Phase-by-Phase Completion Status

| Phase | Spec goal | Status | Notes |
|---|---|---|---|
| 1 | Canonical internal artifacts | Partially implemented | Core artifact types and bundle are real, but compiler output still omits `ClaimArtifact`, does not generate synthesis artifacts in normal ingest, and the markdown sink still bridges through compatibility DTOs. |
| 2 | Refactor writer into `MarkdownVaultSink` | Fully implemented | `MarkdownVaultSink` is the real publishing path and `VaultWriter` is now a thin compatibility wrapper. |
| 3 | Plugin manifest system and public plugin APIs | Partially implemented | Manifest validation and discovery exist, but the install story, plugin ergonomics, and broader public API surface are still minimal. |
| 4 | Add a second sink | Fully implemented | `JsonExportSink` plus `CompositeSink` prove sink independence. |
| 5 | Richer read model with relationship edges | Partially implemented | Read-model notes and edges exist with incremental refresh, but retrieval still relies heavily on separate FTS rebuilding and limited edge types. |
| 6 | Refine maintenance pipeline and real Deep mode | Partially implemented | Maintenance planning/execution exists, but deep mode still differs more by budget and follow-up tasks than by a truly distinct compilation strategy. |

## 3. Major Architectural Areas

| Area | Status | Audit summary |
|---|---|---|
| Canonical artifact model | Partially implemented | Strong core models in `app/artifacts/models.py`, but normal ingest only materializes source/topic/entity/concept/relationship/evidence. `ClaimArtifact` is absent and synthesis generation is maintenance-only. |
| Sink architecture | Fully implemented | `ArtifactSink`, `MarkdownVaultSink`, `JsonExportSink`, `CompositeSink`, and sink registry wiring are in place and used by ingest. |
| Read model and relationship layer | Partially implemented | `ReadModelStore` is real and useful, but the broader retrieval path is still split between read model, vault scanning, and separate FTS rebuilding. |
| Plugin foundation | Partially implemented | Manifest parsing, compatibility checks, discovery, and category-based loading work, but plugin ownership boundaries are still early-stage and not all declared categories have meaningful runtime consumers yet. |
| Prompt system | Fully implemented | Layered composition, prompt packs, workspace/profile overrides, and prompt inspection are all present. |
| Maintenance architecture | Partially implemented | Structural, semantic, synthesis-candidate, and storage refresh tasks exist, but the semantic/synthesis depth remains intentionally conservative. |
| Automation behavior | Partially implemented | Queue-based discovery/processing/maintenance is solid, but balanced and deep modes still share the same ingest graph and differ mostly through budgets and maintenance scope. |
| Storage tiers / large evidence | Fully implemented | Blob-backed evidence preservation under `.system/blobs/` is wired into the markdown sink and source note metadata. |
| Packaging / setup / doctor / docs | Fully implemented | CLI packaging, setup wizard, doctor checks, and repo/docs hygiene are all strong enough for a v2 foundation. |

## 4. Detailed Findings

### 4.1 Canonical Artifact Model

**Status:** Partially implemented

What matches the spec:

- `SourceArtifact`, `TopicArtifact`, `EntityArtifact`, `ConceptArtifact`, `RelationshipArtifact`, `EvidenceReference`, and `SynthesisArtifact` are defined in [`app/artifacts/models.py`](/Users/joeljacobstephen/Code/projects/epistora/app/artifacts/models.py).
- ingest builds an `ArtifactBundle` before publishing through sinks
- name normalization against existing vault state is implemented in [`app/artifacts/builder.py`](/Users/joeljacobstephen/Code/projects/epistora/app/artifacts/builder.py)

What remains incomplete:

- `ClaimArtifact` is still missing
- normal ingest does not create synthesis artifacts
- the markdown sink still uses [`app/artifacts/compat.py`](/Users/joeljacobstephen/Code/projects/epistora/app/artifacts/compat.py) to translate artifacts into legacy knowledge DTOs before rendering

Assessment:

- the canonical layer is real enough to anchor v2
- it is not yet the sole internal representation all the way to render-time

### 4.2 Sink Architecture

**Status:** Fully implemented

What matches the spec:

- sink contract in [`app/sinks/base.py`](/Users/joeljacobstephen/Code/projects/epistora/app/sinks/base.py)
- primary markdown sink in [`app/sinks/markdown_vault.py`](/Users/joeljacobstephen/Code/projects/epistora/app/sinks/markdown_vault.py)
- second machine-facing sink in [`app/sinks/json_export.py`](/Users/joeljacobstephen/Code/projects/epistora/app/sinks/json_export.py)
- multi-sink composition in [`app/sinks/composite.py`](/Users/joeljacobstephen/Code/projects/epistora/app/sinks/composite.py)

Notes:

- this is one of the strongest v2 areas in the repo
- the default sink remains excellent, which is exactly what the spec wanted

### 4.3 Read Model and Relationship Layer

**Status:** Partially implemented

What matches the spec:

- derived SQLite read model in [`app/read_model/store.py`](/Users/joeljacobstephen/Code/projects/epistora/app/read_model/store.py)
- incremental refresh and full rebuild
- relationship edges for wikilinks and source-to-topic/entity/concept mappings

What still falls short:

- retrieval is not consistently layered through the read model
- [`app/retrieval/search.py`](/Users/joeljacobstephen/Code/projects/epistora/app/retrieval/search.py) still rebuilds FTS directly on query instead of treating the derived layer as the primary retrieval substrate
- relationship coverage is useful but narrow relative to the spec’s broader graph ambitions

Assessment:

- the read model foundation exists
- the retrieval architecture is still only partially migrated onto it

### 4.4 Plugin Foundation

**Status:** Partially implemented

What matches the spec:

- manifest validation in [`app/plugins/manifest.py`](/Users/joeljacobstephen/Code/projects/epistora/app/plugins/manifest.py)
- discovery/loading in [`app/plugins/loader.py`](/Users/joeljacobstephen/Code/projects/epistora/app/plugins/loader.py)
- plugin hooks for connectors, backends, prompt packs, and sinks

What still falls short:

- `install_requirements` are declared but not enforced
- some declared plugin categories are accepted by the manifest layer without a substantial runtime integration story yet
- the public plugin authoring API is still fairly implicit

Assessment:

- extension is now a product direction in code, not just in theory
- it is still a foundation, not a mature plugin platform

### 4.5 Prompt System

**Status:** Fully implemented

What matches the spec:

- layered prompt composition in [`app/compiler/prompts.py`](/Users/joeljacobstephen/Code/projects/epistora/app/compiler/prompts.py)
- prompt-pack plugin support
- workspace/profile/user/backend-specific overlays
- inspectable composed prompt object

Assessment:

- this area closely matches the intent of the v2 spec

### 4.6 Maintenance Architecture

**Status:** Partially implemented

What matches the spec:

- planner in [`app/maintenance/planner.py`](/Users/joeljacobstephen/Code/projects/epistora/app/maintenance/planner.py)
- executor in [`app/maintenance/service.py`](/Users/joeljacobstephen/Code/projects/epistora/app/maintenance/service.py)
- structural, semantic, synthesis-candidate, and storage maintenance classes

What still falls short:

- semantic maintenance is still conservative section refresh, not a richer knowledge-refinement pipeline
- synthesis maintenance writes candidate notes, not deeper canonical cross-source artifacts
- storage maintenance is mostly read-model and search refresh, not broader tier-management work

Assessment:

- maintenance is no longer “just lint”
- it is still lighter than the full ambition in the spec

### 4.7 Automation Behavior

**Status:** Partially implemented

What matches the spec:

- discovery stages into a durable queue
- processing is mode-aware
- maintenance can run after processing
- run tracking and retry behavior are in place

What still falls short:

- balanced and deep both use the same enriched ingest path in [`app/automation/processing.py`](/Users/joeljacobstephen/Code/projects/epistora/app/automation/processing.py)
- deep mode differs more by limits and maintenance scope than by a materially different compiler strategy
- legacy interval-worker code still coexists with the newer queue-first scheduling model

Assessment:

- the automation redesign landed
- the mode semantics are not yet as differentiated as the spec implies

### 4.8 Storage Tiers / Large Evidence

**Status:** Fully implemented

What matches the spec:

- hot/warm/cold-style evidence handling in [`app/storage/evidence.py`](/Users/joeljacobstephen/Code/projects/epistora/app/storage/evidence.py)
- blob preservation under `.system/blobs/`
- blob metadata surfaced into raw and source notes

Assessment:

- this is sufficient for v2 foundation status

### 4.9 Packaging / Setup / Doctor / Docs

**Status:** Fully implemented

What matches the spec:

- CLI packaging and scripts in [`pyproject.toml`](/Users/joeljacobstephen/Code/projects/epistora/pyproject.toml)
- setup wizard in [`app/cli/setup_wizard.py`](/Users/joeljacobstephen/Code/projects/epistora/app/cli/setup_wizard.py)
- doctor checks in [`app/cli/doctor.py`](/Users/joeljacobstephen/Code/projects/epistora/app/cli/doctor.py)
- broad documentation set under [`docs/`](/Users/joeljacobstephen/Code/projects/epistora/docs)

Assessment:

- this area is in good shape

## 5. Deviations from the Original v2 Spec

### 5.1 Intentional or Pragmatic Deviations

1. `SourceContent` fills the role the spec describes as `SourceBundle`.
2. discovery currently moves connector output into queue/state models rather than a first-class `DiscoveredItem` model.
3. the markdown sink still uses a compatibility bridge instead of rendering directly from canonical artifacts.
4. query/API support remains intentionally conservative, with the older query path still present as a fallback.

### 5.2 Deferred Spec Features

1. `ClaimArtifact`
2. richer trust/disagreement handling
3. deeper retrieval plugins
4. downstream SDK/MCP-style integration surface
5. a more differentiated “real Deep mode”

## 6. Code Quality Review

### 6.1 Dead Code / Temporary Compatibility

- [`app/vault/writer.py`](/Users/joeljacobstephen/Code/projects/epistora/app/vault/writer.py) is compatibility code, but it is still intentionally used by tests and helpers.
- [`app/automation/worker.py`](/Users/joeljacobstephen/Code/projects/epistora/app/automation/worker.py) and [`app/automation/scheduler.py`](/Users/joeljacobstephen/Code/projects/epistora/app/automation/scheduler.py) are legacy-era scheduling paths and should eventually be retired in favor of the queue-first one-shot runner.
- [`app/models/knowledge.py`](/Users/joeljacobstephen/Code/projects/epistora/app/models/knowledge.py) duplicates part of the artifact model as render DTOs.

### 6.2 Hidden Coupling / Ownership Boundaries

- markdown rendering still depends on artifact-to-legacy translation, which weakens the artifact/sink boundary
- retrieval behavior is split across read model, FTS, and direct vault scanning
- automation still carries both the new queue runner and the old interval worker

### 6.3 Weak Tests / Missing Coverage

The suite is strong overall, but before this audit it was missing coverage for one real bug:

- `JsonExportSink` failed when `JSON_EXPORT_DIR` was configured outside the vault root even though absolute export roots are allowed by settings

That case is now covered in [`tests/test_artifacts.py`](/Users/joeljacobstephen/Code/projects/epistora/tests/test_artifacts.py).

## 7. Fixes Made During This Audit

### 7.1 JSON Export Sink Path Handling

Fixed in [`app/sinks/json_export.py`](/Users/joeljacobstephen/Code/projects/epistora/app/sinks/json_export.py):

- `JsonExportSink.publish()` no longer assumes the export path is always under the vault root
- when the JSON export root is outside the vault, the recorded `VaultUpdate.path` now falls back to the absolute export path instead of raising `ValueError`

Test added in [`tests/test_artifacts.py`](/Users/joeljacobstephen/Code/projects/epistora/tests/test_artifacts.py).

### 7.2 Local macOS Automation Rotation

Verified and updated local machine state:

- the loaded LaunchAgent had been using an older repo-local command/log layout
- it was regenerated onto the current one-shot queue-based runner shape
- it was restarted successfully
- a post-restart run completed cleanly with no stderr output

## 8. Validation Run

### Repo Validation

- `uv run ruff check .` -> passed
- `uv run pytest` -> passed (`312 passed`)

### Live Environment Validation

- `uv run epistora doctor` -> all checks passed
- `uv run epistora ingest latest --limit 1` -> no new items, because the discovery cursor was already current
- latest actual Raindrop bookmark was fetched directly and then force-ingested:
  - URL: `https://x.com/openaidevs/status/2042369696608239848?s=12`
  - result: source note and raw capture were written successfully
- macOS LaunchAgent `com.epistora.automation` was regenerated and restarted
- post-restart automation status showed:
  - enabled: `yes`
  - mode: `deep`
  - last run summary: `discover=0 process=0 failed=0`
  - last run timestamp: `2026-04-10 03:07:16.215737+00:00`

## 9. Technical Debt That Still Remains

1. Direct artifact-to-markdown rendering should eventually replace the compatibility DTO layer.
2. Retrieval should move more decisively onto the derived read model instead of rebuilding search directly on query.
3. Balanced and deep automation modes should diverge in actual compilation behavior, not only in budgets and maintenance scope.
4. Legacy interval-worker automation should be retired once migration is complete.
5. Plugin APIs need a more explicit and durable public contract if third-party plugin growth is a real product goal.

## 10. Recommended Immediate Follow-Ups

1. Move retrieval/search to consume the read model as the primary derived layer.
2. Decide whether `ClaimArtifact` is needed for the intended v2 release line; if not, say so explicitly in docs.
3. Remove or formally deprecate the legacy worker/scheduler path.
4. Tighten deep-mode behavior so it does more than “same ingest path plus broader follow-up.”
5. Replace the compatibility render bridge once the markdown sink can consume canonical artifacts directly.

## 11. Ready-for-v2 Statement

**Yes, with an important qualifier.**

The implementation now matches the v2 spec **well enough to serve as the v2 foundation**:

- the core architectural direction is implemented
- the main extension seams exist
- the storage/sink/prompt/automation/read-model foundations are real
- the repository is test-clean and operational in a live local run

But it should not be described as “the v2 spec is fully complete” without qualification. Several areas are still correctly classified as **partially implemented foundations** rather than fully matured v2 systems.
