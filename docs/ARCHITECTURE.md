# Epistora Architecture

## Purpose

Epistora is a local-first knowledge compiler. It turns saved links and direct
URLs into a markdown vault that is designed to work well for both humans and
filesystem-capable agents.

Today the system has four primary runtime paths:

1. Ingest a single URL or recent inbox items into the vault.
2. Query the vault through direct agent navigation or the read-model-native
   query service.
3. Lint the vault for structural and semantic quality issues.
4. Discover and process queued items through the queue-based automation system.

The repository is organized around those paths rather than around a single web
application or a single model provider.

## Current v2-Aligned Boundaries

The runtime now has explicit boundaries that match the v2 direction:

```text
SourceItem -> SourceContent -> ArtifactBundle -> configured sinks
                                         |
                                         +-> markdown vault (default)
                                         +-> JSON export (optional)
                                         +-> read-model refresh from vault files
```

That means Epistora is no longer only a markdown writer internally, even though
the markdown vault remains the primary default output.

The pre-release hardening pass also adds three small but durable seams around
that core:

- a bounded maintenance contract
- a minimal internal event taxonomy
- lifecycle and derived-work metadata hooks

## Architectural Principles

- Local-first outputs: the durable product is the vault on disk, not an API
  response.
- Raw evidence is immutable: `raw/` captures are written once and then treated
  as source-of-truth evidence.
- Compiled knowledge is maintained: `wiki/` notes are the curated, mergeable,
  updateable knowledge layer.
- Scratch outputs stay separate: `outputs/` is for temporary answers and other
  generated artifacts that are not yet promoted into durable knowledge.
- State is explicit: SQLite stores processing state, sync cursors, queue state,
  and the derived read model, but not the knowledge content itself.
- Backend-agnostic reasoning: ingest, query, and lint call a backend router
  rather than hard-coding one LLM path.
- Agent-first querying: the preferred query workflow is to point Claude Code,
  OpenCode, Codex, or another filesystem-capable agent at the vault and let it
  navigate the vault files directly.

## High-Level Topology

```text
                        CLI / FastAPI / Automation Runner
                                     |
                                     v
                          Services / Orchestrators
                                     |
         +---------------------------+---------------------------+
         |                           |                           |
         v                           v                           v
    Connectors + Fetchers       LangGraph Workflows        Queue Automation
         |                           |                           |
         +-------------+-------------+-------------+-------------+
                       |                           |
                       v                           v
                Backend Router                SQLite State
         (API / OpenCode / Claude / Codex)    + Read Model
                       |
                       v
                 Markdown Vault
        raw/ evidence + wiki/ knowledge + outputs/ scratch
```

## Repository Layers

| Area | Main Files | Responsibility |
|------|------------|----------------|
| Interface | `app/cli/main.py`, `app/main.py`, `app/api/` | Operator-facing CLI and HTTP API |
| Services | `app/services/` | Thin application services that invoke graphs or workflows |
| Compiler | `app/compiler/` | LangGraph workflows and prompt/backend integration |
| Artifacts | `app/artifacts/` | Canonical compiler output before sink rendering |
| Connectors | `app/connectors/` | Inbox connectors and source-type fetchers |
| Backends | `app/backends/` | LLM backend abstraction and fallback routing |
| Sinks | `app/sinks/` | Output publishing for markdown vault and JSON export |
| Vault | `app/vault/` | Vault paths, templates, writes, parsing, indexes, logs |
| Read Model | `app/read_model/` | Derived relationship/index helper DB from vault files |
| Retrieval | `app/retrieval/` | Read-model-native retrieval orchestration |
| Storage | `app/storage/` | SQLite schema and repositories for persistent state |
| Automation | `app/automation/` | Queue discovery/processing and legacy worker scheduling |
| Plugins | `app/plugins/` | Local manifest discovery and extension loading |
| Models | `app/models/` | Shared typed models for sources, knowledge, DB rows, and results |

## Runtime Entry Points

### CLI

`app/cli/main.py` is the primary operator interface. The important command
groups are:

- `epistora ingest url <url>`
- `epistora ingest latest --limit N`
- `epistora sync-inbox`
- `epistora lint`
- `epistora rebuild-indexes`
- `epistora reset-generated`
- `epistora automation discover`
- `epistora automation process-pending`
- `epistora automation run-pending`
- `epistora automation status`
- `epistora backend status`
- `epistora vault show`
- `epistora vault use <path>`

`epistora query` remains available as the built-in tool-driven query entry
point, but the recommended path is still direct agent access to the vault.

### FastAPI

`app/main.py` exposes a FastAPI app with:

- `GET /health`
- `POST /ingest/url`
- `POST /ingest/inbox/sync`
- `POST /ingest/raindrop/sync`
- `POST /query`
- `POST /lint`
- `GET /automation/status`
- `POST /automation/discover`
- `POST /automation/process-pending`
- `POST /automation/run-pending`
- `POST /automation/run-sync`
- `POST /automation/run-lint`
- `POST /automation/rebuild-indexes`
- `GET /status`
- `GET /indexes`

Bearer auth is optional and enforced by `app/api/auth.py` only when
`EPISTORA_API_KEY` is configured.

### Automation Runtimes

Epistora currently supports two automation styles:

- The queue-based one-shot runner in `app/automation/runner.py`, which is the
  recommended path and the basis for OS scheduler integration.
- The legacy interval worker in `app/automation/worker.py`, which runs
  recurring sync/lint/index jobs in-process behind a file lock.

The queue-based runner is the v2-first path. It now feeds a bounded maintenance
plan rather than a loose set of post-processing tasks.

## Configuration Model

`app/config.py` defines a single `Settings` object backed by environment
variables. The effective `.env` lookup order is:

1. `EPISTORA_ENV_FILE` if set
2. `.env` in the current working directory
3. project-root `.env` when running inside the repository
4. Epistora home `.env`
5. project-root `.env` again as a final fallback when outside the repo

Important configuration groups:

- Vault and DB: `VAULT_PATH`, `DATABASE_URL`, `LOG_LEVEL`
- Output and storage tiers: `ARTIFACT_SINK_IDS`, `JSON_EXPORT_DIR`,
  `EVIDENCE_BLOB_*`
- Connector config: `RAINDROP_API_TOKEN`, `RAINDROP_COLLECTION_ID`
- Backend ordering: `BACKEND_ORDER_INGEST`, `BACKEND_ORDER_QUERY`,
  `BACKEND_ORDER_LINT`, `BACKEND_ORDER_STRICT`
- Direct API backend: `API_*`
- CLI backends: `OPENCODE_*`, `CLAUDE_CODE_*`, `CODEX_*`
- Extraction behavior: article, YouTube, X, browser-fallback, summarize
- Ingest evidence limits: `INGEST_*`
- Legacy worker scheduling: `SYNC_*`, `AUTO_LINT_*`, `AUTO_REBUILD_INDEXES_*`
- Queue automation: `AUTOMATION_*`
- Plugin selection: `EPISTORA_PLUGIN_DIRS`, `EPISTORA_PROMPT_PACK`

In normal guided setup, `epistora setup` and `epistora vault use` point the
database inside the vault at `VAULT_PATH/.system/epistora.db`.

## Core Data Model

### Source Models

`app/models/source.py` defines the source lifecycle:

- `SourceItem`: metadata before content extraction
- `SourceContent`: normalized extracted content after fetch
- `SourceType`: `article`, `youtube`, `x_thread`, `pdf`, `generic`, `derived_work`
- `DerivedWorkKind`: `derived_analysis`, `session_digest`,
  `crystallized_output`
- `ExtractionQuality`: `full`, `mostly_full`, `partial`,
  `metadata_only`, `failed`

`SourceItem` includes provider-neutral inbox fields:

- `inbox_provider`
- `external_id`
- `provider_metadata`

That keeps state persistence decoupled from any single inbox provider.

`SourceContent` also now carries minimal `lifecycle` metadata so later
confidence, supersession, and staleness work can evolve without a breaking
schema jump.

### Knowledge Models

`app/models/knowledge.py` defines:

- `Topic`
- `Entity`
- `Concept`
- `SynthesisNote`

These models now also carry the same minimal `lifecycle` metadata block.

### Result Models

`app/models/results.py` defines:

- `IngestResult`
- `QueryResult`
- `LintResult`
- `LintIssue`
- `VaultUpdate`

### Persistent State Models

`app/models/db.py` defines lightweight row models for:

- `ProcessedSource`
- `SyncCursor`
- `VaultNoteMapping`

## Connector And Extraction Architecture

### Inbox Connectors

`app/connectors/registry.py` defines the `LinkInboxConnector` protocol and the
connector registry. At the moment, the only built-in inbox connector is
Raindrop:

- `app/connectors/raindrop.py`

Raindrop is used as a saved-link inbox, not as a full-content source. It
supplies bookmark metadata and timestamps. Full content still comes from the
fetcher layer.

### URL Classification

`app/connectors/classifier.py` classifies URLs into source types with a simple
heuristic stack:

- YouTube URL patterns
- X/Twitter URL patterns
- `.pdf` suffixes
- article-ish host and path hints
- fallback to `generic`

### Fetcher Dispatch

`app/connectors/fetchers/__init__.py` dispatches from `SourceType` to the
appropriate fetcher and performs an up-front safe-URL check.

If a generic bookmark carries the tag `article`, dispatch is promoted from the
generic extractor to the article extractor.

### Fetchers

Current built-in fetchers:

- `article.py`
- `youtube.py`
- `x_thread.py`
- `pdf.py`
- `generic.py`
- `browser.py`
- `readability.py`
- `summarize_cli.py`
- `x_api.py`
- `x_mirrors.py`

#### Article Extraction

`app/connectors/fetchers/article.py` uses this flow:

1. Download HTML with `httpx`
2. Extract with `trafilatura`
3. Optionally try `readability-lxml` when trafilatura is weak
4. Optionally try `summarize` as a weak-extraction fallback
5. Optionally try browser-rendered extraction when configured
6. Fall back to metadata-only capture

Important outputs:

- `cleaned_text`
- readable `archived_markdown`
- `raw_capture_kind = readable_article_markdown`
- OG metadata and canonical URL when available

#### YouTube Extraction

`app/connectors/fetchers/youtube.py` uses this flow:

1. Parse the video ID
2. Optionally run `summarize` as the primary extractor
3. Fall back to `youtube-transcript-api`
4. Fall back to `yt-dlp` subtitle extraction when enabled
5. Fetch metadata via noembed-style lookups
6. Fall back to metadata-only if no transcript is available

Important details:

- Manual captions are treated as `full`
- Auto captions are treated as `mostly_full`
- Transcript text is normalized into timestamped sections
- Transcript length may be truncated by `YOUTUBE_TRANSCRIPT_MAX_CHARS`
- Transcript/source metadata is stored in `raw_metadata`
- Raw captures are written as transcript-oriented archives rather than plain
  HTML dumps

#### X/Twitter Extraction

`app/connectors/fetchers/x_thread.py` currently uses six tiers:

1. Official X API
2. Free mirror APIs (`fxtwitter`, `vxtwitter`)
3. oEmbed / noembed
4. `summarize` fallback
5. direct page scrape / OG fallback
6. browser-rendered fallback

The fetcher continuously compares candidates and keeps the strongest available
extraction rather than blindly trusting the first non-empty result.

#### PDF Extraction

`app/connectors/fetchers/pdf.py` downloads the PDF and extracts text with
PyMuPDF. If the file is image-based or otherwise unreadable, the extractor may
return `failed` or a weak result with metadata.

#### Generic Extraction

`app/connectors/fetchers/generic.py` mirrors the article flow at a lower
fidelity:

1. fetch HTML
2. try trafilatura
3. try readability
4. optionally try `summarize`
5. optionally try browser rendering
6. fall back to metadata-only

### summarize Integration Boundary

The summarize integration is intentionally narrow. Fetchers may call
`app/connectors/fetchers/summarize_cli.py`, but summarize output is normalized
back into Epistora's own `SourceContent` model before the rest of the system
sees it.

That means the downstream pipeline does not care whether the evidence came from
trafilatura, YouTube transcripts, `summarize`, or another extractor.

## Backend Architecture

### Supported Backends

`app/backends/registry.py` currently registers four built-in backends:

- `api`
- `opencode`
- `claude_code`
- `codex`

Their shared request/response schema lives in `app/backends/models.py`.

### Router Behavior

`app/compiler/llm.py` builds a cached `BackendRouter` from the current settings.
`app/backends/router.py` handles:

- per-task backend order
- availability checks before use
- execution-time fallback on failure
- structured and unstructured generation
- skip/failure reason propagation

Task names are:

- `ingest`
- `query`
- `lint`

Structured output relies on prompt contracts plus JSON parsing and validation at
the backend boundary.

### Why The Router Matters

The ingest, query, and lint graphs all call the same router helpers:

- `run_text(...)`
- `run_structured(...)`

That keeps model-provider concerns out of the graph definitions and allows the
same graph to work through APIs or local CLI agents.

## Ingest Pipeline

The ingest path is the core of the system. The primary service entry points are:

- `app/services/ingest_service.py::ingest_url`
- `app/services/ingest_service.py::sync_inbox`
- `app/services/ingest_service.py::sync_raindrop`

### Service-Level Flow

For direct URL ingest:

1. validate the URL
2. do an early `processed_sources` duplicate check by URL hash
3. classify the URL into a `SourceType`
4. build a `SourceItem`
5. invoke the ingest graph

For inbox sync:

1. resolve the configured inbox connector
2. load the last sync cursor
3. fetch recent items since that cursor
4. pre-skip already completed items by URL hash unless `--force`
5. invoke the ingest graph for each remaining item
6. advance the sync cursor after the batch

### LangGraph Ingest Workflow

`app/compiler/ingest_graph.py` defines the graph:

```text
fetch -> dedup -> analyse -> extract_knowledge -> write_vault -> persist
                 \-> persist_duplicate
```

The actual nodes are:

- `fetch`
- `dedup`
- `persist_duplicate`
- `analyse`
- `extract_knowledge`
- `write_vault`
- `persist`

### Step 1: Fetch

The `fetch` node:

- dispatches to the source-type fetcher
- produces a normalized `SourceContent`
- computes the content slug
- emits progress events for CLI automation and user feedback

### Step 2: Dedup

The `dedup` node checks SQLite again using richer post-fetch data:

- URL hash
- content hash when available

This second dedup pass matters because content-hash duplicates are only known
after extraction.

If a completed duplicate is found:

- the graph does not rewrite vault files
- `persist_duplicate` refreshes state and appends an ingest log entry
- the graph returns an `IngestResult` with `deduplicated = true`

`force_reingest` bypasses this dedup branch.

### Step 3: Analyse

The `analyse` node is where the source content becomes a compiled note.

It has several important behaviors:

- Metadata-only sources get a deterministic fallback analysis without calling an
  LLM.
- Failed/empty extractions also get a deterministic fallback analysis.
- Non-video sources are clipped to `INGEST_EVIDENCE_MAX_CHARS`.
- Long YouTube transcripts can exceed a single-pass evidence budget, so the
  graph chunk-digests transcript sections with `run_text(...)` before the final
  structured analysis pass.
- The prompt includes existing topic/entity/concept names from the current
  vault, which helps normalize naming and reduce duplicate page drift.
- Source-type-specific prompt fragments are loaded from `prompts/`.

The expected structured analysis includes:

- summary
- `5-Minute Read`
- detailed reading note
- key ideas
- detailed outline
- important examples
- actionable takeaways
- notable quotes
- best-for audience
- consume recommendation
- why-it-matters
- open questions
- topics
- entities
- concepts

If the backend call fails, the graph still produces a readable provisional note
from the extracted text and records a warning in the `IngestResult`.

### Step 4: Extract Knowledge Objects

The `extract_knowledge` node converts the analysis payload into typed
`Topic`, `Entity`, and `Concept` objects.

Important normalization behavior:

- existing vault pages are scanned first
- names are matched by slug and by a simplified canonical key
- new extracted names are rewritten onto existing page titles when an obvious
  match already exists

This keeps the wiki layer more stable across repeated ingest runs.

### Step 5: Write The Vault

The `write_vault` node uses `app/vault/writer.py`.

Write order:

1. raw capture
2. source note
3. topic pages
4. entity pages
5. concept pages
6. rebuilt indexes

Current write behavior:

- raw captures are immutable once created
- source notes are rewritten on reingest
- topic/entity/concept pages merge new references into existing pages
- indexes are always rebuilt after a successful write phase

### Step 6: Persist State

The `persist` node updates:

- `processed_sources`
- `vault_notes`
- `wiki/logs/ingest-log.md`

It returns the final `IngestResult`.

## What Gets Written To The Vault

### Directory Layout

The vault layout is defined in `app/vault/paths.py`.

```text
<vault>/
  AGENTS.md
  raw/
    articles/
    videos/
    threads/
    pdfs/
    misc/
  wiki/
    sources/
      articles/
      videos/
      threads/
      pdfs/
      misc/
    topics/
    entities/
      people/
      companies/
      tools/
    concepts/
    synthesis/
    indexes/
    logs/
  outputs/
    answers/
    digests/
    reports/
  .system/
    manifests/
    cache/
    state/
    archives/
```

### Raw Capture Layer

Raw captures preserve extracted evidence and are never updated after the first
write. Depending on source type, they may contain:

- readable article markdown
- YouTube transcript captures
- thread/post captures
- PDF text
- weak or metadata-only evidence

### Source Note Layer

`app/vault/templates.py` writes source notes with frontmatter fields such as:

- `type`
- `source_url`
- `source_type`
- `author`
- `published_date`
- `ingested_at`
- `tags`
- `topics`
- `entities`
- `concepts`
- `word_count`
- `extraction_quality`
- `extraction_method`
- `extraction_fallback_chain`
- `raw_capture_path`
- `raw_capture_kind`
- optional `canonical_url`

The source note body is intentionally structured for both humans and agents,
with sections like:

- coverage and limits
- key ideas
- detailed outline
- examples
- takeaways
- quotes
- related notes
- open questions

YouTube and article notes also get source-specific sections.

### Hub Pages

Topic, entity, and concept pages are mergeable hub pages. Existing pages are
read back, their important sections are preserved, and new source references and
related links are merged in rather than overwritten blindly.

### Indexes

`app/vault/index_updater.py` rebuilds:

- `INDEX.md`
- `TOPICS.md`
- `ENTITIES.md`
- `CONCEPTS.md`
- `START_HERE.md`
- `QUERY_PROTOCOL.md`

These indexes are part of the architecture, not mere documentation. They are
the navigation layer that makes the vault usable as an agent workspace.

### Logs

`app/vault/log_updater.py` manages:

- append-only ingest logging in `wiki/logs/ingest-log.md`
- lint report output in `wiki/logs/lint-log.md`

## Query Architecture

### Preferred Query Path: Direct Agent Navigation

Epistora is architected for agent-first querying. The recommended path is:

1. agent opens `AGENTS.md`
2. agent reads `wiki/indexes/START_HERE.md`
3. agent reads `wiki/indexes/QUERY_PROTOCOL.md`
4. agent follows indexes and wikilinks through `wiki/`
5. agent escalates to `raw/` only when evidence quality is weak or exact text
   matters

The knowledge vault template under `knowledge_vault_template/` seeds that
navigation layer when a vault is initialized.

### Query Service

The built-in query path now lives in `app/services/query_service.py` and uses
`app/retrieval/orchestrator.py`.

Current flow:

```text
read-model candidates -> typed relationship expansion -> lexical support ->
LLM answer -> optional save
```

What it does:

- resolves initial candidates from the derived read model
- expands to related artifacts using typed edges such as topic membership,
  source support, backlinks, and derived-from relationships
- uses lexical search from `read_model_fts` only as a supporting signal
- constructs structured context for the configured query backend
- optionally saves the answer to `outputs/answers/<slug>.md`

Important nuance: query saving writes to `outputs/answers/`, not to
`wiki/synthesis/`. Promotion into durable synthesis is still a manual decision.

### Retrieval Stack

`app/retrieval/orchestrator.py` coordinates retrieval, and
`app/read_model/store.py` owns both the relationship layer and lexical support.

Current behavior:

- the read model lives at `.system/state/read_model.db`
- searchable note types are `source`, `topic`, `entity`, `concept`, and
  `synthesis`
- the markdown sink refreshes the read model incrementally after publish
- maintenance can trigger a full read-model rebuild when needed
- lexical support lives in the same derived state as the relationship layer
- the legacy standalone `search.db` runtime has been retired

## Maintenance Architecture

`app/maintenance/` now behaves as a real subsystem with explicit task types and
bounded write scopes.

The current task set is:

- `artifact_neighborhood_refresh`
- `structural_repair`
- `hub_refresh`
- `backlink_repair`
- `candidate_synthesis_refresh`
- `read_model_refresh`
- `search_refresh`

Planning is read-model-aware, ordered, and mode-sensitive:

- `safe` runs structural and storage maintenance only
- `balanced` expands to first-degree hub neighborhoods
- `deep` expands farther and can write candidate synthesis notes

Deep mode is still not a separate ingest compiler, but it is no longer only
"balanced plus a bigger budget". The deeper maintenance neighborhood and
candidate synthesis refresh make it materially different in runtime behavior.

## Event Hooks

`app/events.py` defines a small internal taxonomy for future automation and
integration growth:

- `source_ingested`
- `artifact_written`
- `maintenance_completed`
- `query_answer_saved`
- `scheduled_maintenance_tick`

These are internal hooks, not a public event bus contract yet.

## Lint Architecture

`app/compiler/lint_graph.py` defines the lint graph:

```text
scan -> structural -> llm_lint -> report
```

### Scan

`scan_vault(...)` loads all markdown notes except hidden files and `.system/`.

### Structural Lint

The rule-based lint pass currently checks for:

- source notes missing raw-capture links
- source notes whose raw capture path no longer exists
- source notes with no topic/entity/concept links
- orphan non-source pages
- missing backlinks
- weak topic/entity/concept pages with too few supporting sources
- missing pages that are referenced repeatedly

### LLM Lint

The optional semantic lint pass asks the configured lint backend to identify:

- duplicate candidates
- contradictions
- missing pages
- navigation gaps
- thin pages

If the backend call fails, lint still returns the structural issues it already
found.

### Report Output

The final lint result is written to `wiki/logs/lint-log.md` and returned as a
`LintResult`.

## Automation Architecture

Epistora now has a queue-based automation subsystem and a legacy interval worker.

### Queue-Based Automation

This is the recommended automation path. The key modules are:

- `app/automation/discovery.py`
- `app/automation/processing.py`
- `app/automation/runner.py`
- `app/automation/queue_store.py`
- `app/automation/models.py`

### Discovery Flow

`discover_new_items(...)` does this:

1. resolve the inbox connector
2. load the connector sync cursor
3. fetch recent bookmarks
4. skip URLs already present in the queue
5. skip URLs already completed in `processed_sources`
6. insert new items into `queued_items`
7. advance the sync cursor only after items are durably staged

This separation between discovery and processing is one of the major current
architectural differences from the older direct-sync model.

### Queue Item Lifecycle

Queue statuses are defined in `app/automation/models.py`:

- `discovered`
- `processing`
- `completed`
- `retryable_failed`
- `permanent_failed`
- `skipped_duplicate`

### Processing Flow

`process_pending_items(...)` does this:

1. reset stale `processing` items back to `discovered`
2. load pending queue items ordered by oldest `saved_at`
3. compute the enrichment budget for the chosen mode
4. process each item
5. record attempts and next-retry state

Failure classification is explicit and drives retry behavior:

- network
- rate limit
- extraction
- backend unavailable
- timeout
- unsupported
- unknown

Retry scheduling uses exponential backoff.

### Automation Modes

The automation modes are:

- `safe`
- `balanced`
- `deep`

As implemented today:

- `safe` fetches content, writes the raw capture, writes a minimal source note
  built from deterministic fallback analysis, persists `processed_sources`, and
  rebuilds indexes without using an LLM.
- `balanced` uses the full ingest graph with LLM enrichment, but is constrained
  by per-run enrichment budgets.
- `deep` also uses the full ingest graph with LLM enrichment, with its own
  default backend ordering and the same budget machinery.

The important nuance is that `balanced` and `deep` still do not use different
ingest graphs. The difference now lives in maintenance behavior as well as
operational policy: deep mode expands a broader neighborhood and can generate
candidate synthesis drafts, while balanced mode does not.

### One-Shot Automation Runner

`run_automation(...)` in `app/automation/runner.py` is the end-to-end queued
workflow:

```text
discover -> process_pending -> optional maintenance
```

It records a run in `automation_runs`, emits progress events, and can also run:

- bounded maintenance planning/execution
- optional lint
- structural index rebuilds and read-model refresh work through the maintenance contract

### Legacy Worker

The legacy worker path still exists:

- `app/automation/worker.py`
- `app/automation/scheduler.py`
- `app/automation/jobs.py`
- `app/automation/locks.py`

It uses:

- a file lock for single-process exclusion
- an in-process interval scheduler
- three job types: sync, lint, rebuild indexes

This path does not use the queue-based discovery/processing split.

### Scheduler Helpers

`app/automation/scheduler_helpers.py` generates OS-specific scheduler artifacts
for the queue-based runner:

- macOS launchd
- Linux systemd
- Windows Task Scheduler XML

## Persistent State And Databases

### Main SQLite Database

`app/storage/sqlite.py` manages the main SQLite database with:

- WAL mode
- schema bootstrap
- lightweight migrations

The main tables are:

- `processed_sources`
- `sync_cursors`
- `vault_notes`

`processed_sources` is the dedup and ingest ledger. `vault_notes` is a
lightweight mapping ledger for generated note paths and note types. It is not a
replacement for reading the vault itself.

### Queue Tables

`app/automation/queue_store.py` creates queue automation tables in the same
database:

- `queued_items`
- `automation_runs`
- `item_attempts`

### Read-Model Retrieval State

Retrieval uses the derived read-model database at:

- `.system/state/read_model.db`

That database contains both typed relationship edges and the integrated lexical
search table used by the built-in query service.

## Vault Parsing And Read Model

`app/vault/parser.py` defines `VaultNote`, which is the read model for:

- retrieval
- index rebuilding
- linting
- API status endpoints

`VaultNote` derives note type from frontmatter when present, or from the path
convention when frontmatter is incomplete.

`scan_vault(...)` intentionally ignores `.system/`, because `.system/` contains
internal state rather than knowledge content.

## Reset And Rebuild Behavior

`app/services/reset_service.py` provides the clean reset path used by
`epistora reset-generated`.

What it clears:

- `raw/`
- `wiki/sources/`
- `wiki/topics/`
- `wiki/entities/`
- `wiki/concepts/`
- `wiki/synthesis/`
- `wiki/indexes/`
- `wiki/logs/`
- `outputs/answers/`
- `outputs/digests/`
- `outputs/reports/`
- `.system/cache/`
- `.system/manifests/`
- `.system/state/`

What it preserves:

- vault root
- `AGENTS.md`
- user configuration

It can archive the removed artifacts under `.system/archives/` before clearing
them, then recreates placeholder indexes/logs and truncates the relevant
database tables.

## Current End-To-End Pipelines

### Single URL Ingest

```text
epistora ingest url
  -> ingest_service.ingest_url
  -> classify URL
  -> fetch SourceContent
  -> dedup by URL/content hash
  -> analyse with backend router or deterministic fallback
  -> extract topics/entities/concepts
  -> write raw + source + hub pages
  -> rebuild indexes
  -> persist SQLite state
  -> append ingest log
```

### Inbox Sync Ingest

```text
epistora ingest latest / sync-inbox
  -> connector.fetch_since(cursor)
  -> pre-skip completed URLs
  -> run ingest graph per item
  -> update sync cursor
```

### Agent-First Query

```text
agent reads AGENTS.md
  -> START_HERE.md
  -> QUERY_PROTOCOL.md
  -> index files
  -> relevant wiki pages
  -> raw evidence only if needed
```

### Built-In Query

```text
epistora query / POST /query
  -> resolve read-model candidates
  -> expand typed relationships
  -> apply lexical support
  -> build structured context
  -> query backend answer
  -> optionally save to outputs/answers
```

### Queue Automation

```text
automation discover
  -> stage queued_items

automation process-pending
  -> safe mode minimal write OR enriched ingest graph

automation run-pending
  -> discover
  -> process
  -> optional lint + index rebuild
```

## Extension Points

### Add A New Inbox Connector

Implement `LinkInboxConnector` and register it in
`app/connectors/registry.py`. The rest of the queue/discovery and ingest stack
already speaks in `SourceItem`.

### Add A New Source Fetcher

Add a new fetcher that returns `SourceContent` and update
`app/connectors/fetchers/__init__.py` dispatch as needed.

### Add A New Reasoning Backend

Implement `ReasoningBackend`, register it in `app/backends/registry.py`, and
add it to backend ordering config.

### Add New Vault-Derived Views

The vault is the durable product, so additional read-side features should
usually derive from `scan_vault(...)`, existing frontmatter conventions, or the
read model rather than duplicating knowledge into a second database.

## Known Architectural Tensions

- `balanced` and `deep` automation currently share the same enriched ingest
  implementation, so their difference is mostly budget and backend policy.
- The main DB and queue tables coexist cleanly, but the vault itself remains
  the true knowledge store, so features that need complete knowledge must still
  read markdown rather than relying only on SQLite.

## Summary

Epistora is best understood as a markdown-vault compiler with explicit runtime
state around it:

- connectors discover links
- fetchers turn links into normalized evidence
- LangGraph workflows compile evidence into notes
- the backend router supplies reasoning without coupling the app to one model
- the vault is the durable knowledge product
- SQLite tracks processing, sync, queue, and search state
- queue automation is now the preferred unattended execution path
- agent-first vault navigation is the preferred query path
