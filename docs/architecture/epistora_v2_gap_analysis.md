# Epistora v2 Gap Analysis

Status: Phase 0 repository audit and phased implementation planning

Source of truth for target direction:
- [`docs/epistora_v_2_architecture_spec.md`](/Users/joeljacobstephen/Code/projects/epistora/docs/epistora_v_2_architecture_spec.md)

This report is grounded in the current repository as it exists now, including the recently added canonical artifact layer from Phase 1.

## Executive Summary

Epistora is already structurally closer to the v2 direction than a typical early CLI project. It has:

- a clear evidence extraction boundary around `SourceItem` and `SourceContent`
- a queue-based automation system
- a backend router
- an editable prompt system
- a vault-first output architecture
- a lightweight retrieval stack
- a new canonical artifact layer that now sits between analysis and markdown rendering

The biggest remaining gaps are not basic architecture gaps. They are boundary gaps:

- the markdown vault is still the only real sink
- the writer is still a vault-specific renderer rather than a sink implementation
- retrieval still behaves like a search helper, not a derived read model with relationship edges
- plugin/extensibility is still registry-and-config based rather than a formal plugin product surface
- maintenance remains mostly lint plus rebuild tasks rather than a full improvement pipeline
- balanced and deep automation modes still differ mostly in policy, not in compilation behavior

The safest next implementation order for this repo is:

1. formalize the current vault writer as a `MarkdownVaultSink`
2. define sink-facing compiler publish contracts and keep current output stable
3. add plugin manifests/public extension interfaces
4. add a second sink to prove output independence
5. build a richer derived read model with incremental indexing
6. evolve maintenance and real deep-mode processing on top of that foundation

## Current Architecture Map

### Current Ingest Flow

Main entry points:

- [`app/services/ingest_service.py`](/Users/joeljacobstephen/Code/projects/epistora/app/services/ingest_service.py)
- [`app/compiler/ingest_graph.py`](/Users/joeljacobstephen/Code/projects/epistora/app/compiler/ingest_graph.py)

Current flow:

```text
URL or inbox item
  -> classify URL
  -> fetch SourceContent
  -> dedup by URL/content hash
  -> analyse source
  -> build ArtifactBundle
  -> render vault notes
  -> persist SQLite state
```

Important implementation details:

- evidence extraction is normalized into `SourceContent`
- ingest analysis still happens in the LangGraph ingest graph
- existing knowledge names are scanned from the vault to stabilize topic/entity/concept naming
- compiler output is now an `ArtifactBundle` from [`app/artifacts/`](/Users/joeljacobstephen/Code/projects/epistora/app/artifacts)
- markdown rendering still happens immediately after compilation via [`app/vault/writer.py`](/Users/joeljacobstephen/Code/projects/epistora/app/vault/writer.py)

### Current Vault Writer / Output Path

Main modules:

- [`app/vault/writer.py`](/Users/joeljacobstephen/Code/projects/epistora/app/vault/writer.py)
- [`app/vault/templates.py`](/Users/joeljacobstephen/Code/projects/epistora/app/vault/templates.py)
- [`app/vault/paths.py`](/Users/joeljacobstephen/Code/projects/epistora/app/vault/paths.py)
- [`app/vault/index_updater.py`](/Users/joeljacobstephen/Code/projects/epistora/app/vault/index_updater.py)

Current visible output remains:

```text
vault/
  AGENTS.md
  raw/
  wiki/
    sources/
    topics/
    entities/
    concepts/
    synthesis/
    indexes/
    logs/
  outputs/
  .system/
```

Current behavior:

- raw captures are immutable once written
- source notes and hub pages are rewritten or merged
- indexes are rebuilt after successful writes
- scratch outputs remain in `outputs/`

Important v2-relevant nuance:

- current output is still hardwired to markdown vault semantics
- the new artifact layer feeds the writer, but there is no sink abstraction yet

### Current Storage / State Model

Main modules:

- [`app/storage/sqlite.py`](/Users/joeljacobstephen/Code/projects/epistora/app/storage/sqlite.py)
- [`app/storage/repositories.py`](/Users/joeljacobstephen/Code/projects/epistora/app/storage/repositories.py)
- [`app/automation/queue_store.py`](/Users/joeljacobstephen/Code/projects/epistora/app/automation/queue_store.py)

Current state layers:

- `processed_sources` for ingest ledger and dedup
- `sync_cursors` for discovery cursors
- `vault_notes` for lightweight note mappings
- `queued_items`, `automation_runs`, and `item_attempts` for automation
- `.system/state/search.db` for FTS search

What storage is not doing yet:

- there is no dedicated derived read-model database with relationships
- there is no separate sink/output manifest layer
- there is no blob tier under `.system/blobs/`
- there is no artifact persistence layer beyond immediate rendering and existing ledgers

### Current Retrieval / Query Flow

Main modules:

- [`app/compiler/query_graph.py`](/Users/joeljacobstephen/Code/projects/epistora/app/compiler/query_graph.py)
- [`app/retrieval/search.py`](/Users/joeljacobstephen/Code/projects/epistora/app/retrieval/search.py)
- [`app/retrieval/indexer.py`](/Users/joeljacobstephen/Code/projects/epistora/app/retrieval/indexer.py)
- [`app/retrieval/resolver.py`](/Users/joeljacobstephen/Code/projects/epistora/app/retrieval/resolver.py)

Current reality:

- preferred query path is still direct filesystem agent navigation
- the built-in query graph remains present as a deprecated fallback
- retrieval uses FTS plus fallback lexical matching
- query currently rebuilds FTS on demand before searching
- resolver logic is simple slug/path lookup rather than relationship expansion

This means retrieval exists, but it is not yet the layered read-model design described in v2.

### Current Automation Flow

Main modules:

- [`app/automation/discovery.py`](/Users/joeljacobstephen/Code/projects/epistora/app/automation/discovery.py)
- [`app/automation/processing.py`](/Users/joeljacobstephen/Code/projects/epistora/app/automation/processing.py)
- [`app/automation/runner.py`](/Users/joeljacobstephen/Code/projects/epistora/app/automation/runner.py)
- [`app/automation/queue_store.py`](/Users/joeljacobstephen/Code/projects/epistora/app/automation/queue_store.py)

Current queue flow:

```text
discover
  -> stage queued_items
process
  -> safe mode OR full ingest graph
maintain
  -> optional lint and index rebuild
```

What already aligns with v2:

- durable staged queue
- explicit status model
- retry/failure classification
- one-shot OS scheduler integration

What does not align yet:

- balanced and deep are not truly different compilation paths
- maintenance is still shallow
- queue records do not yet track artifact IDs produced by compilation

### Current Plugin / Extensibility Story

Relevant modules:

- [`app/connectors/registry.py`](/Users/joeljacobstephen/Code/projects/epistora/app/connectors/registry.py)
- [`app/backends/registry.py`](/Users/joeljacobstephen/Code/projects/epistora/app/backends/registry.py)
- [`app/compiler/prompts.py`](/Users/joeljacobstephen/Code/projects/epistora/app/compiler/prompts.py)

What exists:

- inbox connector protocol and registry
- backend factory registry
- prompt directory override via `EPISTORA_PROMPTS_DIR`
- fetcher dispatch by source type

What does not exist:

- plugin manifests
- compatibility/version declarations
- installable plugin packages
- isolated plugin loading and failure boundaries
- plugin-owned sinks, retrieval providers, or maintenance providers

This is extensibility by source code modification, not yet extensibility as a product feature.

### Current Prompt System

Relevant modules:

- [`app/compiler/prompts.py`](/Users/joeljacobstephen/Code/projects/epistora/app/compiler/prompts.py)
- [`prompts/README.md`](/Users/joeljacobstephen/Code/projects/epistora/prompts/README.md)

What exists:

- prompt files live on disk
- users can override prompt directory
- source-type-specific guidance and overrides exist
- system/query/lint/ingest prompt separation exists

What is still missing versus v2:

- formal prompt-pack abstraction
- layered prompt composition beyond current helper functions
- workspace/profile/user override structure
- explicit prompt composition debugging surface

### Current Maintenance / Lint Behavior

Relevant modules:

- [`app/compiler/lint_graph.py`](/Users/joeljacobstephen/Code/projects/epistora/app/compiler/lint_graph.py)
- [`app/services/lint_service.py`](/Users/joeljacobstephen/Code/projects/epistora/app/services/lint_service.py)
- [`app/automation/jobs.py`](/Users/joeljacobstephen/Code/projects/epistora/app/automation/jobs.py)

Current maintenance is mostly:

- structural lint
- optional LLM lint
- index rebuild
- manual or scheduled reset/rebuild operations

What is missing:

- synthesis maintenance
- semantic merge/refactor workflows
- storage-tier maintenance
- read-model repair and incremental freshness tracking
- artifact neighborhood maintenance after ingest

## Gap Analysis Against The v2 Spec

### Already Exists

- local-first markdown vault as the primary user-facing artifact
- immutable raw evidence policy
- `SourceItem` and `SourceContent` as a normalized evidence boundary
- source-type-aware extractor stack for article, YouTube, X, PDF, and generic
- queue-based discovery and processing model
- backend router for reasoning providers
- prompt files on disk with override support
- agent-first query philosophy and seeded vault navigation files
- scheduler helpers for macOS, Linux, and Windows
- canonical artifact layer introduced in Phase 1

### Partially Exists

- discovery layer
  - normalized enough for current connectors, but only Raindrop is built in
- compiler layer
  - now produces canonical artifacts, but immediately renders to markdown without a sink interface
- knowledge model layer
  - core artifacts exist, but they are not yet used as the persisted substrate for other outputs
- sink layer
  - markdown output exists, but only as a vault writer rather than a sink boundary
- retrieval/read model
  - FTS and parser exist, but not a relationship-aware derived read model
- prompt architecture
  - editable prompts exist, but not prompt packs or formal composition layers
- extension surface
  - registries/protocols exist, but not plugin manifests or installable extension boundaries
- maintenance system
  - lint exists, but not a full semantic/synthesis/storage maintenance framework

### Conflicts With The v2 Direction

- current writer still owns rendering concerns directly rather than implementing a sink contract
- retrieval rebuilds FTS on demand during query instead of maintaining an incremental read model
- built-in query graph still assumes search-plus-answer instead of read-model-assisted navigation
- queue modes `balanced` and `deep` still differ mostly by budget/backend policy rather than actual compiler behavior
- storage under `.system/` is incomplete relative to the target layout
  - no dedicated `db/`, `blobs/`, or `jobs/` structure
- plugin-like extension points still require editing core code or environment config

### Missing Entirely

- explicit sink interfaces and sink registry
- second sink such as JSON export or Notion
- derived read model with artifact relationships and freshness metadata
- artifact persistence/manifests beyond current ledgers
- plugin manifest format and compatibility validation
- retrieval provider plugins
- maintenance plugin framework
- prompt pack installation/distribution model
- storage tiering for large raw evidence and blobs
- trust/claim/disagreement layer beyond note text
- SDK/MCP/export pipeline use of canonical artifacts as a first-class substrate

## Refactoring Needed Before Later Features Land Cleanly

These are the main places where the current repo will need refactoring before new features can be added cleanly.

### 1. Vault Writer To Sink Boundary

Current issue:

- [`app/vault/writer.py`](/Users/joeljacobstephen/Code/projects/epistora/app/vault/writer.py) is still effectively the only output implementation
- current compatibility layer translates artifacts back into markdown-oriented inputs

Why refactor first:

- multiple sinks will stay awkward until markdown writing is treated as one sink among many

### 2. Legacy Knowledge Models As Compatibility Objects

Current issue:

- [`app/models/knowledge.py`](/Users/joeljacobstephen/Code/projects/epistora/app/models/knowledge.py) remains useful for compatibility, but it should not continue to grow as the main compiler model

Why refactor first:

- otherwise the repo will drift into parallel object systems with unclear ownership

### 3. Retrieval Search Rebuild Behavior

Current issue:

- query currently rebuilds FTS opportunistically rather than maintaining a proper derived read model

Why refactor first:

- relationship-aware query help and scalable maintenance depend on a stable read-model boundary

### 4. Registry-Only Extension Points

Current issue:

- connectors/backends/prompts are extendable in code, but not through a formal plugin product boundary

Why refactor first:

- sink plugins and retrieval plugins will otherwise turn into more hardcoded registries

### 5. Maintenance Scope Is Too Narrow

Current issue:

- lint plus rebuild is not enough to support v2’s “vault improves over time” goal

Why refactor first:

- true deep mode should depend on a better maintenance contract, not bolt more work into the current ingest graph

## Safest Implementation Order

This is the safest concrete order for this repo as it exists now.

### Phase 1: Canonical Internal Artifact Model

Status:
- now implemented in current repo state

Why it came first:

- it created the compiler/output boundary without forcing a sink rewrite first

Dependencies:
- none

### Phase 2: Markdown Vault Sink Refactor

Goal:

- turn the current vault writer into an explicit markdown sink that consumes canonical artifacts

Why next:

- current behavior can stay stable while removing markdown-specific assumptions from compiler code
- later second-sink work depends on this boundary

Estimated areas:

- [`app/vault/writer.py`](/Users/joeljacobstephen/Code/projects/epistora/app/vault/writer.py)
- [`app/vault/templates.py`](/Users/joeljacobstephen/Code/projects/epistora/app/vault/templates.py)
- [`app/compiler/ingest_graph.py`](/Users/joeljacobstephen/Code/projects/epistora/app/compiler/ingest_graph.py)
- new sink package/interface modules

Backward-compat risks:

- accidental vault output drift
- hub merge behavior regressions
- coupling mistakes between sink contracts and current indexes/logs

### Phase 3: Plugin Foundation And Public Extension APIs

Goal:

- add plugin manifest format and public extension boundaries for connectors, backends, prompt packs, and sinks

Why in this order:

- pluginizing current behavior before sink refactor would bake in the wrong output boundary

Estimated areas:

- connector/backend registries
- config loading
- plugin discovery/manifest code
- docs and doctor checks

Backward-compat risks:

- configuration churn
- loader complexity
- plugin failure handling leaking into core runtime

### Phase 4: Second Sink Proof

Goal:

- add a second sink, preferably JSON export, to prove canonical artifacts are not markdown-only

Why here:

- validates the new sink boundary before larger retrieval and maintenance work

Estimated areas:

- new sink implementation
- compiler publish contracts
- output configuration

Backward-compat risks:

- output duplication confusion
- artifact publication ordering bugs

### Phase 5: Read Model Foundation

Goal:

- introduce a derived read model with relationship edges and incremental indexing

Why here:

- it should consume stable canonical artifacts and sink outputs rather than being designed around the older vault-only assumptions

Estimated areas:

- [`app/retrieval/`](/Users/joeljacobstephen/Code/projects/epistora/app/retrieval)
- parser/indexer split
- `.system` database layout
- query helpers

Backward-compat risks:

- stale read-model state
- mismatches between vault truth and derived indexes

### Phase 6: Maintenance Architecture And Real Deep Mode

Goal:

- expand maintenance from lint/rebuild into structural, semantic, synthesis, and storage maintenance
- make deep mode materially different from balanced mode

Why here:

- deep maintenance depends on canonical artifacts, sink boundaries, and a read model

Estimated areas:

- automation runner
- maintenance services
- lint graph evolution
- read-model repair/freshness

Backward-compat risks:

- surprise write amplification
- unstable maintenance outputs
- over-aggressive synthesis/merge behavior

## Recommended First Implementation Phase

This section is included because the original Phase 0 scope required it.

Given the current repo, the correct first implementation phase was:

### Recommended First Implementation Phase: Canonical Internal Artifact Model

Current status:
- already implemented in current repo state

Exact scope boundaries:

- add canonical artifact models for source/topic/entity/concept/relationship/synthesis/evidence
- keep `SourceContent` as the evidence-layer output
- make ingest produce canonical artifacts before rendering
- keep markdown vault output unchanged
- do not introduce sink interfaces yet
- do not redesign retrieval yet
- do not add plugin manifests yet
- do not change public CLI/API behavior

Why this was the correct first move:

- it removed the most important structural blocker without forcing premature sink or plugin work
- it made later Phase 2 sink refactoring possible without a rewrite of ingest first

## Risks And Ambiguities

### 1. Current Repo State Already Includes Phase 1

This audit is being completed after Phase 1 work exists in the working tree. That means the “recommended first phase” is partly historical and partly validated by the current implementation.

### 2. `docs/ARCHITECTURE.md` Is Locally Modified

The file exists and remains useful context, but this report should be treated as more current because it is cross-checked against implementation files and current repo state.

### 3. “Partially Exists” Can Be Misleading

Several areas use the right words already:

- artifacts
- read model
- plugin-like extension
- maintenance

But in many cases the repo still has only the first 40 to 60 percent of the v2 boundary, not the full architecture.

### 4. Legacy Query Path Still Exists

This is acceptable for backward compatibility, but it should not drive the design of future retrieval/read-model work.

## Phase Completion Assessment

Phase 0 is fully complete after this report because the requested deliverable now exists and covers:

- current architecture mapping
- current vs v2 comparison
- safest implementation order and dependencies
- concrete phased plan for this repo
- refactoring prerequisites
- recommended first implementation phase with exact boundaries

## Concise Recommendations

- Treat Phase 1 as complete and avoid reopening the artifact-model debate.
- Make Phase 2 a sink-boundary refactor, not a feature phase.
- Do not start read-model or plugin work before markdown sink boundaries are explicit.
- Keep backward compatibility by preserving current vault layout through Phase 2.
