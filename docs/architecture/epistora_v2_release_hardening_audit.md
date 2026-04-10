# Epistora v2 Release Hardening Audit

**Date:** 2026-04-10  
**Spec:** `docs/epistora_v_2_architecture_spec.md`  
**Prior audit baseline:** `docs/architecture/epistora_v2_final_audit.md`  
**Audit scope:** release-hardening verification and cleanup for pre-release v2

## 1. Overall Status

Epistora is now ready to be treated as a strong **v2 foundation** for open-source release.

The main release-hardening goals for retrieval/query and maintenance/deep-mode
future-proofing are complete:

- retrieval is now centered on the derived read model
- the built-in query/runtime path uses one coherent v2-native retrieval flow
- the legacy query graph and standalone search stack were removed
- maintenance no longer keeps a separate legacy search index alive
- maintenance is now planned and executed through a bounded task contract
- deep mode now differs from balanced mode through real maintenance behavior,
  not only budget policy
- internal event hooks and lifecycle metadata seams are now present
- derived work has a first-class source/artifact lane
- docs/tests/CLI/API now describe the same retrieval story

The repository still has intentionally bounded v2 seams, but they are now clearer and cleaner rather than half-migrated.

## 2. Biggest Issues Found

1. The deprecated query graph and standalone retrieval stack were still active in runtime.
   - `app/compiler/query_graph.py`
   - `app/retrieval/search.py`
   - `app/retrieval/indexer.py`
   - `app/retrieval/resolver.py`
   - `app/services/query_service.py`, `epistora query`, and `POST /query` still depended on them

2. Maintenance still preserved the removed retrieval architecture.
   - `refresh_search_index` remained in the maintenance contract
   - `.system/state/search.db` was still treated as first-class state

3. Contributor-facing docs and tests still described the old split retrieval story.
   - deprecated CLI/API wording
   - query-graph references in docs
   - tests still asserted the legacy search/index behavior

## 3. What Was Removed

- `app/compiler/query_graph.py`
- `app/retrieval/search.py`
- `app/retrieval/indexer.py`
- `app/retrieval/resolver.py`
- the maintenance task `refresh_search_index`
- query-time FTS rebuild behavior
- deprecated query labeling on `epistora query` and `POST /query`

## 4. What Was Implemented

### Retrieval/query hardening

- Added a read-model-native retrieval orchestrator in `app/retrieval/orchestrator.py`
- Replaced `app/services/query_service.py` internals with:
  - read-model candidate resolution first
  - typed relationship expansion
  - lexical search as a supporting signal only
  - structured context generation for answer synthesis
- Kept query saving behavior stable: outputs still go to `outputs/answers/`

### Read-model hardening

- Extended `ReadModelStore` to own lexical retrieval in the same DB
- Added `read_model_fts` alongside the note/edge/state tables
- Stabilized typed relationship coverage with:
  - `topic_membership`
  - `entity_mention`
  - `concept_relationship`
  - `backlink`
  - `source_support`
  - `derived_from`
- Added query helpers for:
  - structured candidate resolution
  - lexical support search
  - excerpt generation

### Maintenance contract hardening

- Maintenance now plans one stable task set:
  `artifact_neighborhood_refresh`, `structural_repair`, `hub_refresh`,
  `backlink_repair`, `candidate_synthesis_refresh`, `read_model_refresh`,
  `search_refresh`
- Storage maintenance now means read-model refresh/rebuild plus integrated
  lexical-state refresh only
- Legacy standalone search-index refresh is gone
- Deep maintenance now differs from balanced by second-degree neighborhood
  expansion and bounded candidate synthesis refresh, without introducing a
  second retrieval architecture

### Event, lifecycle, and derived-work hooks

- Added a small internal event taxonomy in `app/events.py`
- Wired event publication into ingest, vault writes, maintenance completion,
  scheduled maintenance ticks, and saved query answers
- Added minimal lifecycle metadata hooks to source, knowledge, and artifact
  models plus vault frontmatter serialization
- Added `derived_work` as a future-compatible source/artifact class with
  bounded kinds for work-derived outputs

### Docs/tests cleanup

- Updated contributor-facing docs to describe a single read-model-centered retrieval story
- Updated query, read-model, maintenance, and backend tests
- Added migration coverage for safe retirement of legacy `search.db` state

## 5. Migrations Applied

### Read-model schema/state migration

- `ReadModelStore` now tracks schema version `2`
- Opening the read model performs a rebuild-safe schema migration when older state is detected
- Because the read model is derived, migration safely resets and repopulates helper state rather than preserving stale query indexes

### Legacy search state retirement

- `.system/state/search.db` is now obsolete
- The read-model store removes that file when opening the retrieval DB
- Lexical retrieval now lives inside `.system/state/read_model.db`

### Caller migration

- CLI query path migrated in `app/cli/main.py`
- API query path migrated in `app/api/routes_query.py`
- service runtime migrated in `app/services/query_service.py`
- maintenance planner/executor migrated in `app/maintenance/planner.py` and `app/maintenance/service.py`
- automation maintenance summaries migrated in `app/automation/runner.py`

## 6. Stable Architectural Seams

These seams now look stable enough for the v2 foundation:

- canonical artifact bundle -> sink publishing
- markdown sink -> incremental read-model refresh
- read model -> retrieval/query substrate
- maintenance planner -> bounded structural/semantic/synthesis/storage tasks
- progress/event hooks across ingest, discovery, processing, and automation callbacks
- lifecycle metadata flow across source fetch, vault frontmatter, and processed-source ledgers
- derived-work artifacts can now live in the same durable model without a later
  path migration

## 7. Intentionally Deferred To v2.1

These are real future improvements, but not release blockers for the v2 foundation:

- deeper differentiation between balanced and deep ingest compilation paths
- direct artifact-to-markdown rendering without the current compatibility bridge
- retirement of the legacy interval worker/scheduler path
- broader synthesis generation in normal ingest
- richer plugin-owned retrieval extensions beyond the built-in read-model path
- full confidence scoring, staleness decay, and supersession reasoning

## 8. Verification

Validation run for this pass:

- `uv run pytest -q`
  - result: `318 passed`
- focused regression suite:
  - `uv run pytest tests/test_query_flow.py tests/test_read_model.py tests/test_maintenance.py tests/test_backend_integration.py tests/test_event_hooks.py tests/test_vault_writer.py tests/test_queue_automation.py -q`
  - result: `64 passed`
- `uv run ruff check .`
  - result: clean
- `uv run epistora doctor`
  - result: all checks passed
- `uv run epistora automation maintain --help`
  - result: CLI maintenance help reflects the bounded maintenance contract
- `uv run epistora query --help`
  - result: CLI query path available and documented as the v2 read-model path

Type checks:

- no dedicated type-check command is configured in the repository today

API behavior:

- query route behavior and non-deprecated status are covered by tests

Docs review:

- contributor-facing docs now point to one primary retrieval story
- historical architecture/audit documents still mention the removed legacy path as historical context

## 9. Final Judgment

**Release-hardening status:** complete for the targeted pre-release v2 cleanup.

**Open-source readiness:** yes, with the normal caveat that Epistora is a strong **v2 foundation**, not a finished realization of every long-term v2 ambition in the architecture spec.
