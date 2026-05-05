# Epistora Architecture

## Purpose

Epistora is a local-first knowledge compiler. It takes direct URLs or saved-link
inbox items, extracts evidence, compiles that evidence into canonical artifacts,
publishes those artifacts into one or more local sinks, and maintains a markdown
vault that is optimized for both humans and filesystem-capable agents.

The vault remains the durable product. SQLite supports the runtime, but it does
not replace the vault as the source of truth for knowledge.

The accepted Local Studio direction is recorded in
[`LOCAL_STUDIO_DECISIONS.md`](LOCAL_STUDIO_DECISIONS.md). That document defines
the planned source catalog, provider reference model, Studio API boundary,
frontend packaging approach, and MVP implementation order.

## Current Runtime Boundary

The current system boundary is:

```text
SourceItem
  -> SourceContent
  -> ArtifactBundle
  -> configured sinks
       -> markdown vault (default)
       -> JSON export (optional)
  -> read-model refresh from published markdown
```

Raindrop discovery also writes metadata-only rows into the SQLite source
catalog before staging queue work. This catalog is an operational Studio
foundation; it does not publish markdown notes or replace the completed-source
ledger.

Catalog snapshots can be exported as JSONL under
`.system/exports/source_catalog/`. Each line contains one source plus its
provider refs and normalized tags so metadata-only manual/local rows and
priority state can be restored if the operational DB is lost.

That is the important current shift: Epistora is no longer "fetch content and
write markdown directly". The compiler now has an explicit canonical artifact
layer in the middle, and output publishing is handled by sinks.

## Architectural Principles

- Local-first outputs: the main product is the vault on disk, not an API
  response.
- Evidence-first compilation: fetchers stop at normalized evidence
  (`SourceContent`), then the compiler turns that into canonical artifacts.
- Immutable raw evidence: `raw/` captures are created once and kept as stable
  evidence entrypoints.
- Maintained knowledge layer: `wiki/` notes are rewritten, merged, linted, and
  refreshed over time.
- Explicit scratch layer: `outputs/` holds temporary answers and reports that
  are not automatically promoted into durable knowledge.
- Derived state stays derived: operational SQLite and the read model can be
  rebuilt or refreshed from source inputs and vault files.
- Backend-agnostic reasoning: ingest, query, and lint all route through the same
  backend abstraction instead of binding the app to one model provider.
- Agent-first querying: the preferred way to interrogate knowledge is still to
  let an agent navigate the vault directly.

## High-Level Topology

```text
                   CLI / FastAPI / One-shot automation runner
                                      |
                                      v
                          Services and orchestration layer
                                      |
          +---------------------------+----------------------------+
          |                           |                            |
          v                           v                            v
   Connectors + fetchers       LangGraph compiler/lint      Maintenance + queue
          |                           |                            |
          v                           v                            v
      SourceItem                 ArtifactBundle               Read-model-aware
          |                           |                       maintenance plans
          v                           v
     SourceContent              Sink publishing
                                      |
                   +------------------+------------------+
                   |                                     |
                   v                                     v
            Markdown vault                         JSON export sink
                   |
                   v
     index rebuild + incremental/full read-model refresh
                   |
                   v
         .system/state/read_model.db for built-in retrieval
```

## Repository Layers

| Area | Main Files | Responsibility |
|------|------------|----------------|
| Interface | `app/cli/main.py`, `app/main.py`, `app/api/` | CLI and HTTP entrypoints |
| Services | `app/services/` | Thin application services for ingest, query, lint, reset, topic bundles, and review digests |
| Compiler | `app/compiler/` | LangGraph workflows, prompt composition, backend routing |
| Artifacts | `app/artifacts/` | Canonical internal artifact models and bundle builder |
| Connectors | `app/connectors/` | Inbox connectors, URL classification, fetcher dispatch |
| Backends | `app/backends/` | Reasoning backend abstraction and per-task fallback |
| Sinks | `app/sinks/` | Markdown vault sink, JSON export sink, composite publishing |
| Vault | `app/vault/` | Paths, templates, parsing, indexes, logs, compatibility writer |
| Read Model | `app/read_model/` | Derived note catalog, relationship edges, lexical search |
| Retrieval | `app/retrieval/` | Built-in query retrieval orchestration |
| Maintenance | `app/maintenance/` | Read-model-aware planning and bounded maintenance tasks |
| Automation | `app/automation/` | Queue discovery/processing, one-shot runners, personal-learning preset, legacy worker |
| Storage | `app/storage/` | Main SQLite schema, repositories, evidence storage policy |
| Plugins | `app/plugins/` | Local plugin manifest discovery and runtime loading |
| Models | `app/models/` | Shared source, knowledge, lifecycle, DB, and result models |

## Runtime Entry Points

### CLI

`app/cli/main.py` is the main operator interface. The important current command
groups are:

- core setup and status: `setup`, `doctor`, `help`, `status`
- ingest: `ingest url`, `ingest latest`, `sync-raindrop`, `sync-inbox`
- knowledge health: `lint`, `rebuild-indexes`, `reset-generated`
- personal learning outputs: `views rebuild`, `topic-bundle`,
  `review daily`, `review weekly`
- vault management: `vault show`, `vault use`
- backends and connectors: `backend status`, `backend setup`,
  `connect raindrop`
- automation: `automation setup`, `automation discover`,
  `automation process-pending`, `automation maintain`,
  `automation run-pending`, `automation status`,
  `automation retry-failed`, `automation list-pending`,
  `automation generate-scheduler`, `automation run-personal-learning`

`epistora query` still exists for the built-in retrieval path, but the preferred
query path is still direct agent navigation inside the vault.

### FastAPI

`app/main.py` exposes a FastAPI app with these current route groups:

- health: `GET /health`
- ingest: `POST /ingest/url`, `POST /ingest/inbox/sync`,
  `POST /ingest/raindrop/sync`
- query: `POST /query`
- lint: `POST /lint`
- personal learning outputs: `POST /topic-bundle`, `POST /review/daily`,
  `POST /review/weekly`, `POST /views/rebuild`
- automation: `GET /automation/status`, `POST /automation/discover`,
  `POST /automation/process-pending`, `POST /automation/run-pending`,
  `POST /automation/run-sync`, `POST /automation/run-lint`,
  `POST /automation/rebuild-indexes`
- Local Studio UI: `GET /studio`, assets under `GET /studio/assets/*`
- Local Studio API: `GET /studio/sources` (with `q`, `metadata_only`,
  `source_type`, `display_state`, `provider`, `tag` filters),
  `GET /studio/sources/{source_uid}`,
  `GET /studio/sources/{source_uid}/reader` (compiled note + raw capture +
  parsed frontmatter),
  `POST /studio/sources/manual`,
  `POST /studio/sources/{source_uid}/actions/enqueue`,
  `GET /studio/jobs` (jobs include `source_title`, `source_url`,
  `source_type`, and `attempt_count`),
  `POST /studio/jobs/process-once`,
  `GET /studio/search` (combined catalog + read-model hits with provenance),
  `GET /studio/stats` (catalog/queue/note counts),
  `GET /studio/knowledge/{topic|entity|concept|synthesis}` and
  `GET /studio/knowledge/note/detail` for read-only browsing,
  `POST /studio/snapshots/export`, `POST /studio/snapshots/import`
- read-only status: `GET /status`, `GET /indexes`

Bearer auth is optional and enforced only when `EPISTORA_API_KEY` is set.

The Studio routes are source-catalog-first. Source list/search includes
metadata-only rows from `sources`; source detail returns catalog lifecycle,
provider refs, normalized tags, and latest source-linked processing jobs.
Manual URL add creates or updates a metadata-only catalog row and a `manual`
provider ref, but does not fetch content, write vault notes, publish sinks, or
deep process unless an explicit enqueue action is included.

The Studio UI is a React + Vite frontend under `studio/`, with production
assets built into `studio/static/` for FastAPI serving. It preserves the
editorial parchment palette with serif typography (EB Garamond / Cormorant
Garamond) and is reader-first. The UI offers four nav clusters:

- Library sections: All sources, Articles, Videos / YouTube, Threads,
  Documents, Metadata only, Brief ready, Deep compiled, Needs attention.
  Each section is a filter over `GET /studio/sources`.
- Source detail with reader tabs: Compiled note, Raw capture, Metadata, Jobs.
  Source actions (Capture / Brief / Deep / Refresh) sit in a restrained
  toolbar and reuse `POST /studio/sources/{uid}/actions/enqueue`.
- Knowledge browse: Topics, Entities, Concepts, Synthesis. Read-only over the
  read model, with a vault-scan fallback when the read model is empty.
- Workspace: combined Search, Queue, Settings.

The Studio frontend is intentionally not bound to JSON export shape. Reader
content is delivered as parsed frontmatter, body text, and the original
markdown so the UI can render compiled notes and raw captures without coupling
to durable artifact serialization.

`epistora studio` starts the FastAPI app on `127.0.0.1` by default, chooses a
nearby free port when the preferred port is busy, serves the packaged static
Studio assets, and opens the browser unless `--no-open` is passed.

### Automation Runtimes

Epistora currently has two unattended execution styles:

- queue-based one-shot automation in `app/automation/runner.py`
- legacy in-process interval worker in `app/automation/worker.py`

The queue-based runner is the recommended path and the one reflected by current
OS scheduler generation helpers.

Local Studio adds a bounded source-linked job runner in
`app/services/studio_service.py`. It processes queued `processing_jobs` once,
maps Studio actions to existing modes (`capture`/`refresh` -> safe, `brief` ->
balanced, `deep_compile` -> deep), and reuses `queued_items` processing for
capture/enrichment compatibility. Job status, attempts, errors, timestamps,
queued item links, processed source links, and source lifecycle fields are
updated after each run. Studio does not own a persistent background worker.

## Configuration Model

`app/config.py` defines a single `Settings` object backed by environment
variables. The `.env` lookup order is:

1. `EPISTORA_ENV_FILE` if set
2. `.env` in the current working directory
3. project-root `.env` when running inside the repository
4. Epistora home `.env`
5. project-root `.env` again as a final fallback when outside the repo

Important configuration groups:

- vault and DB: `VAULT_PATH`, `DATABASE_URL`, `LOG_LEVEL`
- sink selection and exports: `ARTIFACT_SINK_IDS`, `JSON_EXPORT_DIR`
- evidence storage tiers: `EVIDENCE_BLOB_DIR`,
  `EVIDENCE_BLOB_THRESHOLD_BYTES`, `EVIDENCE_BLOB_PREVIEW_CHARS`
- connectors: `RAINDROP_API_TOKEN`, `RAINDROP_COLLECTION_ID`
- backend ordering: `BACKEND_ORDER_INGEST`, `BACKEND_ORDER_QUERY`,
  `BACKEND_ORDER_LINT`, `BACKEND_ORDER_STRICT`
- direct API backend: `API_*`
- CLI backends: `OPENCODE_*`, `CLAUDE_CODE_*`, `CODEX_*`
- extraction behavior: article, YouTube, X, browser fallback, summarize
- ingest evidence windows: `INGEST_*`
- queue automation: `AUTOMATION_*`
- plugin and prompt selection: `EPISTORA_PLUGIN_DIRS`,
  `EPISTORA_PROMPT_PACK`, `EPISTORA_PROMPT_PROFILE`,
  `EPISTORA_PROMPT_USER_OVERRIDE`

`epistora setup` and `epistora vault use` normally point the operational
database inside the active vault at `VAULT_PATH/.system/epistora.db`, but the
database location remains configurable.

## Core Data Model

### Evidence and Source Models

`app/models/source.py` defines the evidence boundary:

- `SourceItem`: metadata before fetch/extraction
- `SourceContent`: normalized extracted evidence after fetch
- `SourceType`: `article`, `youtube`, `x_thread`, `pdf`, `generic`,
  `derived_work`
- `DerivedWorkKind`: `derived_analysis`, `session_digest`,
  `crystallized_output`
- `ExtractionQuality`: `full`, `mostly_full`, `partial`,
  `metadata_only`, `failed`

`SourceItem` includes provider-neutral inbox fields:

- `inbox_provider`
- `external_id`
- `provider_metadata`

`SourceContent` carries:

- raw and cleaned evidence text
- archived markdown when available
- extraction quality, method, fallback chain, and notes
- canonical URL and hashes
- raw metadata used by storage tiers and source-note rendering
- lifecycle metadata hooks

### Canonical Artifact Models

`app/artifacts/models.py` defines the compiler output boundary:

- `SourceArtifact`
- `TopicArtifact`
- `EntityArtifact`
- `ConceptArtifact`
- `SynthesisArtifact`
- `RelationshipArtifact`
- `EvidenceReference`
- `ArtifactBundle`

This layer is the main compiler contract. The ingest graph does not publish
markdown-oriented intermediate objects anymore. It builds an `ArtifactBundle`
first, then sinks consume that bundle.

### Legacy Human-Facing Knowledge Models

`app/models/knowledge.py` still defines:

- `Topic`
- `Entity`
- `Concept`
- `SynthesisNote`

These remain useful because the markdown vault sink currently renders through
compatibility adapters in `app/artifacts/compat.py` into the existing markdown
templates. Internally, though, the compiler boundary is now the artifact layer.

### Lifecycle Metadata

`app/models/lifecycle.py` defines shared lifecycle hooks used by sources and
artifacts:

- `confidence`
- `last_confirmed_at`
- `supersedes`
- `superseded_by`
- `staleness_status`
- `reinforcement_count`

These are structural hooks, not a full confidence or freshness engine yet.

### Source Catalog Foundation

`app/models/db.py` and `app/storage/repositories.py` now include the first
Local Studio source catalog layer:

- `sources`: stable opaque source UIDs, URL/content hashes, lifecycle status
  dimensions, tag/provider snapshots, and persisted priority scores.
- `source_provider_refs`: provider sightings such as Raindrop IDs and metadata.
- `source_tags`: normalized tags with origins (`provider`, `user`, `system`,
  or `theme`).
- `processing_jobs` and `processing_attempts`: source-linked work records for
  future Studio actions.
- `usage_events`: explicit accounting records for future budget views.

The existing `queued_items`, `item_attempts`, and `processed_sources` tables
remain in place for current automation and ingest compatibility. Metadata-only
catalog imports are separate from safe-mode capture and do not fetch content or
create vault notes by default.

### Result Models

`app/models/results.py` defines the main runtime result payloads:

- `IngestResult`
- `QueryResult`
- `TopicBundleResult`
- `ReviewDigestResult`
- `LintResult`
- `LintIssue`
- `VaultUpdate`

### Operational Persistence Models

`app/models/db.py` defines lightweight DB row models for:

- `ProcessedSource`
- `SyncCursor`
- `VaultNoteMapping`

## Connector and Extraction Architecture

### Inbox Connectors

`app/connectors/registry.py` defines the `LinkInboxConnector` protocol and the
connector registry. The built-in connector today is:

- `app/connectors/raindrop.py`

Raindrop is treated as a bookmark inbox. It supplies bookmark metadata, tags,
timestamps, and provider IDs. It does not provide the main evidence body for the
compiled pipeline.

### URL Classification

`app/connectors/classifier.py` classifies URLs into source types using a
heuristic stack:

- YouTube URL patterns
- X/Twitter URL patterns
- `.pdf` suffixes
- article-like host/path hints
- fallback to `generic`

### Fetcher Dispatch

`app/connectors/fetchers/__init__.py` owns dispatch and performs an up-front
safe-URL check. The dispatch behavior today is:

- generic sources tagged `article` are promoted to article extraction
- unsupported or unsafe URLs return a failed `SourceContent`
- the dispatcher logs start/end timing and normalizes crash behavior into a
  failed `SourceContent` rather than letting the rest of the ingest pipeline
  explode

### Built-In Fetchers

Primary dispatch targets:

- `article.py`
- `youtube.py`
- `x_thread.py`
- `pdf.py`
- `generic.py`

Supporting helper modules used by those fetchers:

- `browser.py`
- `readability.py`
- `summarize_cli.py`
- `x_api.py`
- `x_mirrors.py`

### Extraction Flows

#### Article

`app/connectors/fetchers/article.py` uses this effective flow:

1. download HTML
2. extract with trafilatura
3. optionally fall back to readability
4. optionally use `summarize` when extraction is weak
5. optionally use browser rendering when configured
6. fall back to metadata-only capture

Important outputs include:

- `cleaned_text`
- readable `archived_markdown`
- `raw_capture_kind = readable_article_markdown`
- OG metadata and canonical URL when available

#### YouTube

`app/connectors/fetchers/youtube.py` currently uses this flow:

1. parse the video ID
2. optionally use `summarize` as the primary extractor
3. fall back to `youtube-transcript-api`
4. optionally fall back to `yt-dlp` subtitle extraction
5. fetch metadata
6. fall back to metadata-only capture

Important details:

- manual captions are treated as `full`
- auto captions are treated as `mostly_full`
- transcript text is normalized into timestamped sections
- transcripts may be capped by `YOUTUBE_TRANSCRIPT_MAX_CHARS`
- transcript provenance is stored in `raw_metadata`

#### X / Twitter

`app/connectors/fetchers/x_thread.py` uses a tiered strategy:

1. official X API
2. mirror APIs
3. oEmbed / noembed
4. `summarize` fallback
5. direct page scrape / OG fallback
6. browser-rendered fallback

It compares candidate extractions and keeps the strongest result rather than
accepting the first non-empty response.

#### PDF

`app/connectors/fetchers/pdf.py` downloads the PDF and extracts text with
PyMuPDF. Image-only or otherwise unreadable PDFs degrade into weak or failed
captures.

#### Generic

`app/connectors/fetchers/generic.py` mirrors the article path at lower fidelity:

1. fetch HTML
2. try trafilatura
3. try readability
4. optionally try `summarize`
5. optionally try browser rendering
6. fall back to metadata-only

### summarize Integration Boundary

The `summarize` integration stays intentionally narrow. Fetchers may call
`app/connectors/fetchers/summarize_cli.py`, but they normalize the output back
into Epistora's own `SourceContent` model before the rest of the system sees it.

Downstream code therefore only cares about normalized evidence, not which
extractor happened to produce it.

## Prompt and Backend Architecture

### Prompt Composition

`app/compiler/prompts.py` implements layered prompt composition for ingest,
query, and lint.

Prompt roots are searched in this order:

1. `EPISTORA_PROMPTS_DIR`
2. active prompt-pack plugin root selected by `EPISTORA_PROMPT_PACK`
3. built-in `prompts/`

Prompt layers are composed in this order:

1. base compiler instructions
2. artifact-type instructions
3. source-type instructions
4. workspace/profile instructions
5. user overrides
6. backend/model-specific hints

Workspace-local prompt guidance can also live under
`<vault>/.system/prompts/`.

### Backend Router

`app/compiler/llm.py` builds a cached `BackendRouter` from current settings.
`app/backends/router.py` handles:

- per-task backend order
- availability checks
- execution-time fallback
- plain-text generation
- structured-output generation
- fallback reason propagation

Task names are:

- `ingest`
- `query`
- `lint`

Built-in backends registered in `app/backends/registry.py` are:

- `api`
- `opencode`
- `claude_code`
- `codex`

The router is shared across ingest, query, and lint, which keeps provider
selection and fallback policy out of the graph definitions.

## Sink and Publishing Architecture

`app/sinks/registry.py` resolves the configured sink set from
`ARTIFACT_SINK_IDS`.

Built-in sinks today are:

- `markdown_vault`
- `json_export`

When multiple sink IDs are configured, `CompositeSink` publishes them in a
deterministic order.

### Markdown Vault Sink

`app/sinks/markdown_vault.py` is the default output path. It:

1. ensures the vault structure exists
2. writes the raw capture, including storage-tier decisions
3. writes the source note
4. merges or creates topic, entity, concept, and synthesis notes
5. rebuilds indexes
6. refreshes the read model with changed paths and rebuilt indexes

The older `app/vault/writer.py` is now only a compatibility alias around this
sink.

### JSON Export Sink

`app/sinks/json_export.py` writes deterministic machine-facing JSON under:

```text
<vault>/.system/exports/json/<source_type>/<slug>.json
```

unless `JSON_EXPORT_DIR` points elsewhere.

The JSON export does not change the compiler. It consumes the same
`ArtifactBundle` as the markdown sink.

## Ingest Pipeline

The ingest path is the core write pipeline. Main service entry points:

- `app/services/ingest_service.py::ingest_url`
- `app/services/ingest_service.py::sync_inbox`
- `app/services/ingest_service.py::sync_raindrop`

### Service-Level Flow

#### Direct URL ingest

1. validate the URL with the HTTP safety helper
2. do an early duplicate check by URL hash in `processed_sources`
3. classify the URL into a `SourceType`
4. build a `SourceItem`
5. invoke the ingest graph

#### Inbox sync ingest

1. resolve the configured inbox connector
2. load the last sync cursor
3. fetch recent items since that cursor
4. pre-skip already completed URLs unless `force`
5. invoke the ingest graph per remaining item
6. advance the sync cursor after the batch

### LangGraph Ingest Workflow

`app/compiler/ingest_graph.py` defines this graph:

```text
fetch -> dedup -> analyse -> extract_knowledge -> write_vault -> persist
                 \-> persist_duplicate
```

Current nodes:

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
- returns normalized `SourceContent`
- computes the slug
- emits progress events

### Step 2: Dedup

The `dedup` node performs a richer post-fetch duplicate pass using:

- URL hash
- content hash when available

If a completed duplicate exists and `force_reingest` is not set:

- the graph does not rewrite vault files
- `persist_duplicate` refreshes ingest state and append-only logging
- the graph returns an `IngestResult` with `deduplicated = true`

### Step 3: Analyse

The `analyse` node is where evidence becomes compiled understanding.

Important current behavior:

- metadata-only captures use deterministic fallback analysis with no LLM call
- failed or empty captures also use deterministic fallback analysis
- non-video evidence is clipped to `INGEST_EVIDENCE_MAX_CHARS`
- very long YouTube transcripts are split into chunks and digested with
  `run_text(...)` before the final structured analysis pass
- prompts include existing topic/entity/concept names from the vault to reduce
  page-title drift
- source-type-specific guidance comes from the layered prompt system

Expected structured analysis fields include:

- summary
- five-minute read
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
from captured text and records a warning in the `IngestResult`.

### Step 4: Extract Knowledge

The `extract_knowledge` node builds an `ArtifactBundle` from the analysis and
the normalized evidence.

Important current behavior:

- existing topic/entity/concept page titles are resolved before artifact
  creation
- bullet-heavy analysis fields are normalized into structured artifact fields
- evidence references are created from the captured source evidence
- explicit relationship artifacts connect the source artifact to topic/entity/
  concept artifacts

### Step 5: Publish Through Sinks

The `write_vault` node does not write vault files directly. It calls the
configured sink set via `build_default_sink(...)`.

For the default markdown sink, publish order is:

1. raw capture
2. source note
3. topic pages
4. entity pages
5. concept pages
6. synthesis pages, if present
7. rebuilt indexes
8. read-model refresh

Current write behavior:

- raw captures are immutable once created
- source notes are rewritten on reingest
- topic/entity/concept pages merge new references into existing pages
- indexes are always rebuilt after publish
- read-model refresh happens after markdown publish

### Step 6: Persist State

The `persist` node updates:

- `processed_sources`
- `vault_notes`
- `wiki/logs/ingest-log.md`

It also publishes the internal `source_ingested` event and returns the final
`IngestResult`.

## Safe Automation Ingest Path

Queue automation `safe` mode is a distinct write path implemented in
`app/automation/processing.py::_process_safe`.

It still follows the same architectural boundary:

```text
fetch -> deterministic fallback analysis -> ArtifactBundle -> sinks -> persist
```

Differences from the full ingest graph:

- no LLM usage
- no LangGraph analyse node
- fallback-only analysis
- usually no topic/entity/concept extraction beyond what deterministic fallback
  yields

Even safe mode now publishes through the canonical artifact and sink layer,
rather than bypassing it.

## Vault Structure and Semantics

The vault layout is defined by `app/vault/paths.py`.

```text
<vault>/
  AGENTS.md
  raw/
    articles/
    videos/
    threads/
    pdfs/
    misc/
    derived/
  wiki/
    sources/
      articles/
      videos/
      threads/
      pdfs/
      misc/
      derived/
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
    blobs/
    archives/
    exports/json/   (optional, created on demand)
```

### Raw Capture Layer

`raw/` is the stable evidence entrypoint. Raw captures are immutable and may
contain:

- readable article archives
- transcript-oriented video captures
- thread captures
- PDF text
- metadata-only or weak captures
- storage-tier metadata that points to cold blobs when needed

### Source Note Layer

`app/vault/templates.py` renders source notes with frontmatter such as:

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
- `canonical_url` when available
- `quick_summary`
- `quick_brief`
- `best_next_action`
- `theme_tags`
- `brief_status`
- `reading_state`
- `watch_verdict` and `watch_verdict_reasoning` for video notes
- `quick_section_guide`, `detailed_sections`, `signal_vs_filler`, and
  `important_terms` when source analysis provides them
- lifecycle metadata
- storage-tier metadata like `raw_storage_tier`, `raw_blob_path`,
  `raw_blob_sha256`

The body is structured for both humans and agents and includes sections like:

- coverage and limits
- overview / quick brief
- best next action
- source-specific watch or read guidance
- quick section guide and section-by-section detail for richer video notes
- summary / short summary
- five-minute read
- detailed reading note
- key ideas
- detailed outline
- examples
- takeaways
- quotes
- related notes
- open questions
- capture notes

### Hub Pages

Topic, entity, and concept pages are mergeable hub pages. Existing pages are
read back, maintenance-managed sections are preserved, and new source references
or related links are merged rather than overwritten blindly.

### Candidate Synthesis Notes

Deep maintenance can create candidate synthesis drafts under `wiki/synthesis/`.
These are durable markdown files, but they are maintenance-generated candidates,
not the default output of ordinary query answering.

### Indexes and Logs

`app/vault/index_updater.py` rebuilds:

- `INDEX.md`
- `TOPICS.md`
- `ENTITIES.md`
- `CONCEPTS.md`
- `START_HERE.md`
- `QUERY_PROTOCOL.md`
- `READING_HOME.md`
- `VIDEOS.md`
- `ARTICLES.md`
- `TOPICS_FEED.md`
- `DASHBOARD.md`

It also writes the optional Obsidian snippet:

- `.obsidian/snippets/epistora-reader-views.css`

`app/vault/log_updater.py` writes:

- append-only ingest log at `wiki/logs/ingest-log.md`
- lint report at `wiki/logs/lint-log.md`
- maintenance report at `wiki/logs/maintenance-log.md`

Indexes are an architectural layer, not incidental documentation. They are part
of the navigation contract for agent-first use.

## Storage Tiers

`app/storage/evidence.py` implements the evidence storage policy.

Current tiers:

- hot: compiled source notes in `wiki/sources/`
- warm: stable immutable raw notes in `raw/`
- cold: oversized payloads under `.system/blobs/`

When a raw payload exceeds the configured threshold:

1. the full payload is written to `.system/blobs/<kind>/<slug>/primary.<ext>`
2. a warm raw note is still written in `raw/`
3. the source note still points to the raw note
4. the raw note points to the blob and records checksum and size metadata

This preserves auditability without forcing the hottest visible layer to carry
the full payload every time.

## Personal Learning Architecture

Personal Learning Mode is a composed preset on top of the normal runtime. It
does not introduce a parallel compiler path.

It coordinates:

- the `personal_learning` prompt profile
- brief-first source-note fields on canonical source artifacts
- deterministic reader views rebuilt from vault metadata
- topic-bundle generation from a frozen retrieved source set
- daily and weekly review digest generation
- queue automation, read-model refresh, and bounded maintenance

The execution-depth modes remain `safe`, `balanced`, and `deep`. The
`personal_learning` preset chooses the workflow; the mode chooses how much
enrichment and maintenance to run.

### Brief-First Source Understanding

`SourceArtifact` now carries durable fields used by personal-learning surfaces:

- `quick_brief`
- `best_next_action`
- `theme_tags`
- `brief_status`
- `watch_verdict` and `watch_verdict_reasoning`
- `quick_section_guide`
- `detailed_sections`
- `signal_vs_filler`
- `important_terms`

`app/artifacts/builder.py` normalizes these from analysis output and assigns
`theme_tags` through deterministic rules in `app/utils/theme_tags.py`. The
markdown sink projects them into source-note frontmatter and top-of-note
sections.

### Reader Views

Reader views are deterministic projections, not durable knowledge artifacts.
`epistora views rebuild` calls the same index rebuild path and writes:

- `wiki/indexes/READING_HOME.md`
- `wiki/indexes/VIDEOS.md`
- `wiki/indexes/ARTICLES.md`
- `wiki/indexes/TOPICS_FEED.md`

These pages rank source notes using `brief_status`, `reading_state`,
`saved_at`/`ingested_at`, source type, and `theme_tags`. They are safe to
regenerate and are not hand-maintained.

### Topic Bundles

`app/services/topic_bundle_service.py` implements topic learning packets.

Flow:

```text
topic query
  -> read-model retrieval context
  -> filter by source type / date window
  -> freeze usable source-note set
  -> topic-bundle prompt
  -> markdown output under outputs/digests/topic-bundles/
```

The service saves immutable per-run output with frontmatter recording the query,
filters, included source paths, topics consulted, source counts, and
`bundle_status`. If the backend call fails or coverage is sparse, it still
returns a limited fallback packet.

### Review Digests

`app/services/review_service.py` implements deterministic daily and weekly
digests.

Daily digests prioritize:

- recent usable source briefs
- explicit `reading_state` preferences
- recurring or preferred `theme_tags`
- at most one older resurfaced item when enough signal exists

Weekly digests prioritize:

- highlights from the ISO week
- recurring themes
- topic-bundle candidates

Digests are gated by usefulness thresholds and are written to:

- `outputs/digests/daily/<YYYY-MM-DD>.md`
- `outputs/digests/weekly/<YYYY-Www>.md`

Review surfacing history is stored in the operational DB so the digest generator
can avoid repeating the same older notes too aggressively.

### Personal Learning Runner

`app/automation/runner.py::run_personal_learning` is the composed runner behind
`epistora automation run-personal-learning`.

Current flow:

```text
discover
  -> process pending queue items with EPISTORA_PROMPT_PROFILE=personal_learning
  -> refresh read model
  -> rebuild reader views
  -> generate daily and weekly review digests
  -> optional bounded maintenance
```

The runner records an automation run with `run_type = personal_learning` and
returns a structured summary for CLI/API reporting.

## Query Architecture

### Preferred Query Path: Direct Agent Navigation

Epistora is still architected for agent-first querying. The recommended path is:

1. read `AGENTS.md`
2. read `wiki/indexes/START_HERE.md`
3. read `wiki/indexes/QUERY_PROTOCOL.md`
4. follow index links and wikilinks through `wiki/`
5. escalate to `raw/` only when evidence quality is weak or exact wording matters

The vault template under `knowledge_vault_template/` seeds that navigation
layer for new vaults.

### Built-In Query Service

The built-in query path lives in `app/services/query_service.py` and uses
`app/retrieval/orchestrator.py`.

Current flow:

```text
read-model candidates
  -> typed relationship expansion
  -> lexical support
  -> structured context assembly
  -> query backend answer
  -> optional save to outputs/answers
```

Important current behavior:

- if no relevant artifacts are found, the service returns a structured fallback
  answer instead of failing
- if the backend call fails, the service returns a grounded fallback listing the
  strongest notes and references
- saved answers go to `outputs/answers/<slug>.md`, not `wiki/synthesis/`
- confidence is currently a simple heuristic based on the number of retrieved
  artifacts

### Retrieval Stack

`app/retrieval/orchestrator.py` coordinates retrieval, and
`app/read_model/store.py` owns the derived state.

Current retrieval behavior:

- structured candidate scoring from note title/path/body and frontmatter-derived
  topic/entity/concept membership
- lexical support from FTS5 in the same read-model database
- neighbor expansion over typed edges such as `topic_membership`,
  `entity_mention`, `concept_relationship`, `source_support`,
  `derived_from`, and `backlink`
- inclusion of index-file previews in the final query context

The built-in query system is therefore read-model-native, but still explicitly
secondary to direct vault navigation.

## Read Model Architecture

The read model is a rebuildable helper DB stored at:

```text
.system/state/read_model.db
```

It is derived from vault files, not authoritative over them.

### Current Schema

`app/read_model/store.py` maintains:

- `read_model_notes`
- `read_model_edges`
- `read_model_state`
- `read_model_fts`

The read model stores:

- note catalog rows
- note type and frontmatter metadata
- bounded normalized note body text
- outgoing wikilinks
- typed relationship edges
- integrated lexical search rows
- refresh and migration state

### Refresh Strategy

The markdown sink refreshes the read model after publish.

Current behavior:

- changed note paths are refreshed incrementally when possible
- rebuilt indexes are also refreshed into the read model
- if a title changes, refresh falls back to a full rebuild because title-based
  link resolution may affect many other notes
- legacy `.system/state/search.db` is retired and removed

## Lint Architecture

`app/compiler/lint_graph.py` defines the lint graph:

```text
scan -> structural -> llm_lint -> report
```

### Scan

`scan_vault(...)` reads all visible markdown files except hidden files and
`.system/`.

### Structural Lint

The rule-based pass currently checks for:

- source notes missing raw-capture links
- source notes whose raw-capture or raw-blob path no longer exists
- source notes with no topic/entity/concept links
- orphan non-source pages
- missing backlinks
- weak topic/entity/concept pages with too few supporting sources
- missing pages that are referenced repeatedly

### LLM Lint

The optional semantic pass asks the configured lint backend for:

- duplicate candidates
- contradictions
- missing pages
- navigation gaps
- thin pages

If the backend fails, lint still returns the structural issues already found.

### Report Output

The final `LintResult` is written to `wiki/logs/lint-log.md` and returned to the
caller.

## Maintenance Architecture

`app/maintenance/` is now a real subsystem with explicit planning and bounded
write scopes.

### Planner Inputs

`MaintenancePlanner` plans from:

- mode: `safe`, `balanced`, `deep`
- optional scope paths
- optional `force_rebuild`
- the current read-model neighborhood

It expands scope differently by mode:

- no scope + `deep`: inspect a thin set of hub pages
- source scope: expand to linked hubs
- hub scope: expand to backlinks
- `deep`: expand farther to second-degree neighbors and supporting sources

### Current Maintenance Tasks

The planner may schedule:

- `artifact_neighborhood_refresh`
- `structural_repair`
- `hub_refresh`
- `backlink_repair`
- `candidate_synthesis_refresh`
- `read_model_refresh`
- `search_refresh`

What they currently do:

- `artifact_neighborhood_refresh`: planning/audit only, no writes
- `structural_repair`: run structural lint and rebuild indexes
- `hub_refresh`: refresh maintenance-managed hub sections
- `backlink_repair`: repair backlink sections on touched hub pages
- `candidate_synthesis_refresh`: write candidate synthesis notes for strong
  topic neighborhoods
- `read_model_refresh`: incremental or full refresh of the derived read-model DB
- `search_refresh`: refresh integrated lexical state inside the same DB

### Mode Differences

- `safe`: structural and storage maintenance only
- `balanced`: add bounded hub and backlink refresh
- `deep`: expand the neighborhood farther and allow candidate synthesis drafts

This is the real current difference between balanced and deep mode. They still
share the same enriched ingest graph, but they no longer behave the same after
ingest.

## Automation Architecture

Epistora currently has a queue-based automation subsystem plus a legacy worker.

### Queue-Based Automation

Main modules:

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
5. skip already completed URLs in `processed_sources`
6. insert new queue rows into `queued_items`
7. stage already-completed URLs as `skipped_duplicate`
8. advance the sync cursor only after staging is durable

This discovery/processing split is one of the biggest current architectural
differences from the older direct-sync path.

### Queue Item Lifecycle

Queue statuses are:

- `discovered`
- `processing`
- `completed`
- `retryable_failed`
- `permanent_failed`
- `skipped_duplicate`

Failures are classified as:

- `network`
- `rate_limit`
- `extraction`
- `backend_unavailable`
- `timeout`
- `unsupported`
- `unknown`

Retry scheduling uses exponential backoff.

### Processing Flow

`process_pending_items(...)` does this:

1. reset stale `processing` items back to `discovered`
2. load pending queue items ordered by oldest `saved_at`
3. compute the enrichment budget for the mode
4. process each item
5. record item attempts and retry metadata

Mode behavior today:

- `safe`: fetch, archive, build fallback analysis, build an `ArtifactBundle`,
  publish through sinks, persist `processed_sources`, no LLM usage
- `balanced`: run the full ingest graph with `force_reingest=True`, subject to
  enrichment caps
- `deep`: run the same full ingest graph with `force_reingest=True`, also
  subject to enrichment caps

Important nuance: `automation_backend_order_safe/balanced/deep` settings exist
in config, but the current processing implementation does not yet wire per-mode
backend router selection into the ingest graph. Balanced and deep currently use
the normal ingest backend routing.

### One-Shot Automation Runner

`run_automation(...)` in `app/automation/runner.py` is the main unattended
pipeline:

```text
discover -> process_pending -> optional maintenance -> optional lint
```

It records a row in `automation_runs`, emits progress events, and reports the
combined summary.

### Legacy Worker

The older worker path still exists:

- `app/automation/worker.py`
- `app/automation/scheduler.py`
- `app/automation/jobs.py`
- `app/automation/locks.py`

It uses:

- a file lock for single-process exclusion
- an in-process interval scheduler
- three recurring job types: sync, lint, rebuild indexes

This path does not use the discovery/processing queue split.

### Scheduler Helpers

`app/automation/scheduler_helpers.py` generates OS-specific scheduler artifacts
for the queue-based runner:

- macOS launchd
- Linux systemd
- Windows Task Scheduler XML

## Event Hooks

`app/events.py` defines a small internal event taxonomy:

- `source_ingested`
- `artifact_written`
- `maintenance_completed`
- `query_answer_saved`
- `topic_bundle_saved`
- `review_digest_saved`
- `scheduled_maintenance_tick`

These are internal hooks for runtime coordination and future integrations, not a
public event-bus contract.

## Persistent State and Databases

### Main Operational SQLite Database

`app/storage/sqlite.py` manages the main SQLite DB with:

- WAL mode
- schema bootstrap
- lightweight migrations

Main tables:

- `processed_sources`
- `sync_cursors`
- `vault_notes`
- `review_surface_history`

`processed_sources` is the ingest ledger and dedup ledger. `vault_notes` is only
a lightweight note mapping table, not a replacement for reading the vault.
`review_surface_history` records notes surfaced in daily/weekly review digests
so resurfacing can avoid excessive repetition.

### Queue Tables

`app/automation/queue_store.py` creates additional tables in the same DB:

- `queued_items`
- `automation_runs`
- `item_attempts`

### Derived Retrieval State

Retrieval uses the separate derived DB at `.system/state/read_model.db`.

Knowledge therefore spans three layers:

- vault files as the durable knowledge product
- main operational DB for processing state
- derived read-model DB for retrieval support

## Plugin Architecture

### Discovery

`app/plugins/loader.py` searches plugin manifests in:

1. paths from `EPISTORA_PLUGIN_DIRS`
2. `<project>/plugins`
3. `<epistora_home>/plugins`

Compatible manifests are loaded into an in-memory `PluginRegistry`.

### What Is Wired Into The Current Runtime

Current runtime loading uses plugins for:

- inbox providers
- reasoning backends
- sinks
- prompt packs

Prompt packs are selected by `EPISTORA_PROMPT_PACK` and contribute prompt roots.

### Manifest Schema

`app/plugins/manifest.py` supports a broader manifest type list:

- `inbox_provider`
- `extractor`
- `reasoning_backend`
- `prompt_pack`
- `sink`
- `maintenance_plugin`
- `retrieval_provider`

Only the categories listed in the previous section are currently wired into the
runtime loaders.

## Reset and Rebuild Behavior

`app/services/reset_service.py` powers `epistora reset-generated`.

It clears generated vault content such as:

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
- `.system/blobs/`

It preserves:

- the vault root
- `AGENTS.md`
- user configuration

It can archive removed content under `.system/archives/`, recreates placeholder
indexes and logs, and truncates these main DB tables:

- `processed_sources`
- `vault_notes`
- `sync_cursors`

Current nuance: reset does not currently clear queue automation tables
(`queued_items`, `automation_runs`, `item_attempts`) in the main DB.

## Current End-to-End Pipelines

### Single URL Ingest

```text
epistora ingest url
  -> ingest_service.ingest_url
  -> URL safety check
  -> early URL-hash duplicate check
  -> classify URL
  -> fetch SourceContent
  -> post-fetch dedup by URL/content hash
  -> analyse with backend router or deterministic fallback
  -> build ArtifactBundle
  -> publish through configured sinks
  -> rebuild indexes and refresh read model
  -> persist SQLite state
  -> append ingest log and emit events
```

### Inbox Sync Ingest

```text
epistora ingest latest / sync-inbox
  -> connector.fetch_since(cursor)
  -> pre-skip completed URLs
  -> run ingest graph per item
  -> advance sync cursor
```

### Queue Automation: Safe

```text
automation discover
  -> stage queued_items

automation process-pending --mode safe
  -> fetch evidence
  -> deterministic fallback analysis
  -> ArtifactBundle
  -> sinks
  -> processed_sources persistence
```

### Queue Automation: Balanced or Deep

```text
automation run-pending --mode balanced|deep
  -> discover
  -> process via full ingest graph
  -> maintenance plan
  -> optional lint
```

### Agent-First Query

```text
agent reads AGENTS.md
  -> START_HERE.md
  -> QUERY_PROTOCOL.md
  -> indexes
  -> wiki notes
  -> raw evidence only if needed
```

### Built-In Query

```text
epistora query / POST /query
  -> read-model structured candidates
  -> lexical support
  -> relationship expansion
  -> query backend answer
  -> optional save to outputs/answers
```

### Topic Bundle

```text
epistora topic-bundle / POST /topic-bundle
  -> read-model retrieval context
  -> source filters and usable-brief thresholding
  -> frozen source set
  -> topic-bundle prompt or deterministic fallback
  -> outputs/digests/topic-bundles/<topic>-<timestamp>.md
  -> topic_bundle_saved event
```

### Review Digest

```text
epistora review daily|weekly / POST /review/daily|weekly
  -> scan source-note metadata
  -> apply brief-status, reading-state, theme, and history heuristics
  -> skip if usefulness threshold is not met
  -> outputs/digests/daily|weekly/<period>.md
  -> review_surface_history update
  -> review_digest_saved event
```

### Personal Learning Preset

```text
automation run-personal-learning
  -> discover from configured inbox connector
  -> process queue with personal_learning prompt profile
  -> refresh read model
  -> rebuild reader views
  -> generate daily and weekly review digests
  -> optional bounded maintenance
```

### Maintenance

```text
automation maintain / runner maintenance step
  -> read-model-aware planning
  -> bounded structural / semantic / synthesis / storage tasks
  -> maintenance log
  -> maintenance_completed event
```

## Extension Points

### Add a New Inbox Connector

Implement `LinkInboxConnector` and register or plugin-load it through
`app/connectors/registry.py`. The rest of the queue and ingest stack already
operates on `SourceItem`.

### Add a New Reasoning Backend

Implement `ReasoningBackend`, register it in `app/backends/registry.py`, or ship
it as a `reasoning_backend` plugin.

### Add a New Sink

Implement the sink interface, register it in `app/sinks/registry.py`, or ship it
as a `sink` plugin. The compiler already emits canonical `ArtifactBundle`s.

### Add a Prompt Pack

Ship a `prompt_pack` plugin and select it with `EPISTORA_PROMPT_PACK`.

### Add a New Fetcher

Add a new fetcher that returns `SourceContent` and wire dispatch in
`app/connectors/fetchers/__init__.py`. Unlike sinks and backends, fetchers are
not yet plugin-loaded in the current runtime.

## Current Architectural Constraints

- The vault is still title-link driven, so read-model incremental refresh falls
  back to full rebuild when note titles change.
- Balanced and deep automation share the same enriched ingest graph; their main
  difference is maintenance behavior and enrichment limits.
- The main DB, queue tables, and read model coexist cleanly, but knowledge still
  lives in markdown, so any feature that needs authoritative knowledge must
  still read vault files.
- Plugin manifests support more categories than the current runtime actively
  loads.
- Reset-generated clears ingest mappings and visible generated artifacts, but it
  does not currently clear queue history tables.

## Summary

Epistora is best understood as a local knowledge compiler with explicit runtime
seams:

- connectors discover URLs
- fetchers normalize evidence into `SourceContent`
- the compiler turns evidence into an `ArtifactBundle`
- sinks publish those artifacts into the markdown vault and optional exports
- the markdown sink rebuilds indexes and refreshes the read model
- query, lint, maintenance, and automation work from the published vault and
  derived state
- the vault remains the durable knowledge product
