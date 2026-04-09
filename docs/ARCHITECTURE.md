# Epistora — Architecture

## System Overview

Epistora is a local-first personal knowledge compiler. It ingests content from saved links, compiles structured knowledge notes, and maintains an agent-queryable Obsidian-compatible vault.

**Query model:** Epistora is agent-first. The primary way to query the vault is to point Claude Code or OpenCode at the vault directory. The vault is structured so direct agents can navigate it effectively using `AGENTS.md`, index files, and the query protocol. The legacy `epistora query` command is deprecated.

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Sources    │     │   Compiler   │     │    Vault     │
│              │────▶│  (LangGraph) │────▶│  (Markdown)  │
│ Raindrop     │     │              │     │              │
│ Direct URLs  │     │ Ingest Graph │     │ Source Notes │
│              │     │ Lint Graph   │     │ Topic Pages  │
│              │     │              │     │ Entity Pages │
└──────────────┘     └──────┬───────┘     │ Concept Pages│
                             │             │ Indexes/Logs │
                      ┌──────▼───────┐     └──────┬───────┘
                      │Backend Router│            │
                      │              │     ┌──────▼───────┐
                      │ API │OC│ CC  │     │ Direct Agent │
                      └──────────────┘     │ (Claude Code │
                             │             │  / OpenCode) │
                      ┌──────▼───────┐     └──────────────┘
                      │   SQLite     │
                      │ (state only) │
                      └──────────────┘
```

## Layer Architecture

### A. Connector Layer (`app/connectors/`)

Responsible for fetching source metadata and content. **Raindrop is used only
as a URL inbox** — it provides saved URLs, title, tags, excerpt, and saved
time. All full-text extraction happens through the fetcher layer.

- **`classifier.py`** — Determines `SourceType` from a URL using regex patterns
- **`raindrop.py`** — `RaindropConnector` calls the Raindrop.io API to fetch saved bookmarks
- **`registry.py`** — `LinkInboxConnector` protocol + connector registry/factory for saved-link inboxes
- **`fetchers/`** — Content extraction by type, each with a multi-tier fallback chain:
  - `article.py` — Trafilatura → readability-lxml → summarize fallback → browser rendering → metadata-only, plus a clean archived article markdown output
  - `youtube.py` — summarize primary → youtube-transcript-api → yt-dlp subtitles → metadata/noembed → ASR hook, plus structured transcript capture
  - `x_thread.py` — Official X API → fxtwitter/vxtwitter → oEmbed/noembed → summarize fallback → page scrape → browser
  - `pdf.py` — PyMuPDF text extraction with PDF metadata
  - `generic.py` — Trafilatura → readability → summarize fallback → browser → metadata-only
  - `browser.py` — Optional Playwright-based rendered extraction (shared by other fetchers)
  - `readability.py` — readability-lxml wrapper (shared by article + generic)
  - `summarize_cli.py` — summarize.sh subprocess wrapper plus normalization into `SourceContent`
  - `x_api.py` — Official X API v2 client for post/thread extraction
  - `x_mirrors.py` — fxtwitter/vxtwitter/oEmbed helpers for free X extraction
- **`utils/extraction.py`** — Shared helpers: quality scoring, OG metadata, URL canonicalization

#### summarize.sh Boundary

summarize is integrated strictly at the **`SourceContent` boundary**:

- fetchers may invoke `summarize_cli.py`
- summarize output is normalized into Epistora's existing `SourceContent` model
- the ingest graph, dedup/state ledger, vault writer, merge logic, and query pipeline stay unchanged

This keeps summarize focused on what it is best at: source extraction,
transcription, and first-pass evidence preparation. It is not the schema owner
for downstream analysis.

#### Extraction Quality Scoring

Every fetcher returns a `SourceContent` with structured extraction metadata:

- **`extraction_quality`**: `full` | `mostly_full` | `partial` | `metadata_only` | `failed`
- **`extraction_method`**: which extractor ultimately produced the content
- **`extraction_fallback_chain`**: ordered list of all methods attempted
- **`extraction_notes`**: human-readable explanation of what happened
- **`raw_metadata`**: provider-specific metadata (OG tags, video info, tweet metrics, etc.)
- **`canonical_url`**: resolved canonical URL when available
- **`archived_markdown`**: clean markdown body for the raw vault layer when available
- **`raw_capture_kind`**: distinguishes readable article archives, transcripts, and generic raw captures

Quality is scored based on word count, paragraph count, title presence, and extractor-specific signals (e.g., auto-captions on YouTube are rated `mostly_full` instead of `full`).

#### Source-Aware summarize Strategy

- **YouTube**: summarize is the optional primary extractor; local transcript paths remain the fallback chain.
- **Articles**: summarize is fallback-only after Trafilatura/readability and before browser rendering.
- **Generic pages**: summarize is fallback-only after the generic extractor and before browser rendering.
- **X/Twitter**: summarize is fallback-only after the X-specific API/mirror/oEmbed tiers.

Weak-extraction detection is explicit and shared. Fetchers trigger summarize
only when the earlier result is too short, too thin, teaser-like, truncated, or
metadata-only.

#### X/Twitter Extraction Strategy

X extraction uses a six-tier fallback:

1. **Official X API** (Tier 1): When `X_API_BEARER_TOKEN` is configured, uses the Twitter v2 API for full post text, thread reconstruction via `conversation_id`, and structured metadata. Optional — never required.
2. **Free mirror APIs** (Tier 2): fxtwitter and vxtwitter provide full tweet text, thread content, and X article expansion via free public endpoints.
3. **oEmbed** (Tier 3): Twitter oEmbed and noembed for basic tweet text.
4. **summarize CLI** (Tier 4): Attempted only when earlier X-specific results are still weak.
5. **Page scrape** (Tier 5): Direct OG metadata extraction.
6. **Browser rendering** (Tier 6): Optional Playwright-based fallback for difficult cases.

**Extensibility:** New connectors implement the same pattern: receive a `SourceItem`, return a `SourceContent`. Adding a `ReadwiseReaderConnector` or `RSSConnector` requires only a new file and registering it in the fetcher dispatcher.

### B. Normalization Layer (`app/models/`)

All data flows through typed Pydantic models:

- **`source.py`** — `SourceItem` (pre-fetch metadata), `SourceContent` (post-fetch normalized content), `SourceType` enum
- **`knowledge.py`** — `Topic`, `Entity`, `Concept`, `SynthesisNote`
- **`results.py`** — `IngestResult`, `QueryResult`, `LintResult`, `VaultUpdate`, `LintIssue`
- **`db.py`** — `ProcessedSource`, `SyncCursor`, `VaultNoteMapping` (SQLite row models)

Inbox-specific persistence uses provider-neutral fields (`provider`,
`external_id`, `provider_metadata`) so the stored state is not coupled to a
single bookmark service.

### C. Backend Layer (`app/backends/`)

The backend layer abstracts over multiple reasoning/LLM execution engines so the rest of the app is backend-agnostic.

#### Design

```
ReasoningBackend (abstract base)
  ├── DirectApiBackend      – OpenAI-compatible API calls via LangChain
  ├── OpenCodeCliBackend    – Shells out to `opencode run`
  └── ClaudeCodeCliBackend  – Shells out to `claude -p`

BackendRouter
  - Holds a registry of backends keyed by stable backend IDs
  - Per-task fallback ordering (BACKEND_ORDER_INGEST, etc.)
  - Selection-time availability check + execution-time fallback
  - Logs every fallback decision
```

#### Why CLI Backends Exist

Not every model or provider is accessible through a simple API endpoint. CLI agent tools like OpenCode and Claude Code:
- Manage their own authentication and model access
- May support models not available through direct APIs
- Enable mixing paid APIs with local/alternative models
- Allow the automation worker to use whatever reasoning tool is installed locally

Built-in backends are registered through `app/backends/registry.py`. Unknown
tokens in `BACKEND_ORDER_*` are ignored with a warning by default, or rejected
when `BACKEND_ORDER_STRICT=true`.

OpenCode receives the composed system + user prompt as one argv element, so
extremely large prompts can still hit OS command-line size limits.

#### Structured Output

All three backends support structured (JSON) output:
- **API backend**: Relies on the model's instruction following to produce JSON
- **CLI backends**: Prompt instructs JSON-only output; response is parsed and validated
- JSON extraction handles markdown fences and surrounding text gracefully
- Optional Pydantic schema validation ensures data integrity

### D. Compiler/Orchestrator Layer (`app/compiler/`)

Uses LangGraph state machines for the three core workflows:

#### Ingest Graph
```
fetch → dedup → analyse → extract_knowledge → write_vault → persist
```
Each node is an async function that transforms the shared `IngestState`.
The LLM is called during `analyse` via `run_structured()`, where the prompt now
produces a richer wiki-ready schema:

- short summary
- `5-Minute Read`
- detailed reading note / articleified video note
- key ideas, outline, examples, takeaways, quotes
- consume recommendation, why-it-matters, open questions
- topics, entities, and concepts

#### Query Graph (DEPRECATED)
```
resolve_context → generate_answer → maybe_save
```
Searches the vault for relevant notes, builds context, and generates a grounded answer via `run_text()` using the "query" task backend.

**This workflow is deprecated.** The preferred query path is direct agent access to the vault. See `AGENTS.md` and `wiki/indexes/QUERY_PROTOCOL.md` for the agent-first query procedure. The query graph code is retained for backward compatibility but no longer recommended.

#### Lint Graph
```
scan_vault → structural_lint → llm_lint → generate_report
```
Combines rule-based checks (orphans, backlinks, weak pages) with LLM-powered semantic analysis via `run_structured()` using the "lint" task backend.

### E. Vault Writer Layer (`app/vault/`)

- **`paths.py`** — All vault path conventions in one place
- **`templates.py`** — Markdown + YAML frontmatter generators for raw captures, source notes, topics, entities, concepts, and synthesis
- **`writer.py`** — `VaultWriter` handles create-or-update logic, including merging source lists
  while keeping raw captures immutable after first write
- **`parser.py`** — `VaultNote` class for reading and introspecting existing notes
- **`index_updater.py`** — Rebuilds INDEX, TOPICS, ENTITIES, CONCEPTS indexes
- **`log_updater.py`** — Appends to ingest log, writes lint reports

### F. Retrieval Layer (`app/retrieval/`)

- **`indexer.py`** — SQLite FTS5 full-text search index over vault markdown
- **`search.py`** — Combined FTS + keyword fallback search
- **`resolver.py`** — Maps names to existing vault pages by slug

### G. Storage Layer (`app/storage/`)

- **`sqlite.py`** — `Database` class with WAL mode and schema auto-migration
- **`repositories.py`** — Repository pattern for processed sources, sync cursors, vault note mappings

### H. Automation Layer (`app/automation/`)

The automation subsystem enables hands-free operation with two complementary approaches:

#### Queue-Based Automation (recommended)

The durable queue-based system separates discovery from processing and supports safe/balanced/deep modes:

- **`models.py`** — Pydantic models: `QueuedItem`, `AutomationRun`, `ItemAttempt`, `AutomationMode`, `QueueItemStatus`, `FailureType`
- **`queue_store.py`** — SQLite-backed durable queue with `QueueRepository`, `AutomationRunRepository`, `ItemAttemptRepository`
- **`discovery.py`** — Discovers new bookmarks from connectors and stages them durably in the queue. Advances the sync cursor only after items are staged.
- **`processing.py`** — Mode-aware processing pipeline. Safe mode: fetch + archive only. Balanced: capped LLM enrichment. Deep: full ingest graph. Includes failure classification, retry with exponential backoff, and partial batch handling.
- **`runner.py`** — One-shot automation runner (`run_automation`): discover → process → maintain → exit. Primary building block for cross-platform scheduling.
- **`scheduler_helpers.py`** — Generates OS-specific scheduler config (macOS LaunchAgent, Linux systemd, Windows Task Scheduler).

#### Legacy Interval-Based Worker (still supported)

- **`worker.py`** — Main loop for `epistora worker`. Acquires a file lock, builds a scheduler, and ticks every 5s until interrupted.
- **`scheduler.py`** — `IntervalScheduler` manages `ScheduledJob` instances. Each job has an interval, an async function, and overlap protection.
- **`jobs.py`** — Individual job functions (`run_sync_job`, `run_lint_job`, `run_rebuild_indexes_job`) that call the existing service layer.
- **`locks.py`** — `FileLock` using `fcntl.flock` for single-machine mutual exclusion.

#### Queue Tables

```sql
queued_items     — durable bookmark queue (status lifecycle: discovered → processing → completed/failed)
automation_runs  — history of automation runs with stats
item_attempts    — per-item attempt history for debugging
```

#### Automation Modes

| Mode | LLM Usage | Behavior |
|------|-----------|----------|
| **safe** | None | Fetch, archive raw, write minimal source note from text extraction |
| **balanced** | Capped | Safe mode + LLM enrichment for a limited number of items per run |
| **deep** | Full | Full ingest graph with topic/entity/concept/wiki updates |

### I. Interface Layer

- **CLI** (`app/cli/main.py`) — Typer-based, primary operator interface
- **API** (`app/main.py` + `app/api/`) — FastAPI with OpenAPI docs

## Data Flow: Ingest

1. User runs `epistora ingest url <url>` or `POST /ingest/url`
2. URL classified → appropriate fetcher called → `SourceContent` produced
   - article-tagged generic bookmarks are promoted into the article extractor
   - article fetches preserve readable raw markdown
   - YouTube fetches preserve transcript captures
3. Dedup check against URL hash / content hash in SQLite
4. Backend router selects best available backend for "ingest" task
5. LLM generates structured analysis (summary, `5-Minute Read`, detailed note, ideas, examples, recommendations, topics, entities, concepts)
   - prompt includes the current vault topic/entity/concept titles to reduce duplicate naming drift
6. Knowledge extraction produces `Topic`, `Entity`, `Concept` models
   - extracted names are normalized back onto existing vault page titles when obvious variants already exist
7. VaultWriter creates/updates:
   - Raw capture → `inbox/raw/{type}/`
   - Source note → `wiki/sources/{type}/`
   - Topic pages → `wiki/topics/`
   - Entity pages → `wiki/entities/`
   - Concept pages → `wiki/concepts/`
8. Indexes rebuilt, ingest log appended, SQLite state updated

## Force Re-run Path

The ingest service and CLI now support force re-runs without deleting vault
state:

- `epistora ingest url --force <url>`
- `epistora sync-inbox --force`
- `epistora sync-raindrop --force`

Internally this bypasses URL/content dedup so the compiled layer can be
regenerated while the raw evidence file remains immutable if it already exists.

## Reset And Re-run Path

`app/services/reset_service.py` implements the clean reset path used for
validation and replay:

- archives existing generated artifacts under `.system/archives/`
- clears generated raw/wiki/output/state directories
- resets processed-source, vault-note, and sync-cursor tables
- recreates index and log placeholders for a clean rerun

The Phase 10 validation for this repository intentionally did **not** use this
reset path; it reprocessed only the latest Raindrop bookmark in place.

## Data Flow: Backend Routing

```
Graph node calls run_structured(task="ingest", ...)
        │
        ▼
BackendRouter.generate_structured()
        │
        ├── Try API backend → available? → execute → success? → return
        │                                              │
        │                                              └── fail → log
        ├── Try OpenCode backend → available? → execute → success? → return
        │                                                   │
        │                                                   └── fail → log
        └── Try Claude Code backend → ... → return or error
```

## Future Extensibility

Adding a new backend (e.g., Ollama, Gemini):

1. Create `app/backends/ollama.py` implementing `ReasoningBackend`
2. Add `BackendType.OLLAMA` to the enum
3. Register in `get_backend_router()` in `app/compiler/llm.py`
4. Add config settings; all downstream usage works unchanged

Adding a new source connector (e.g., Readwise Reader):

1. Create `app/connectors/readwise.py` implementing fetch methods
2. Register in `app/connectors/fetchers/__init__.py` if it provides a content fetcher
3. Add a sync command to CLI and API route
4. All downstream processing (compile, write, index) works unchanged

## Agent-First Query Architecture

The vault is designed so that direct filesystem-capable agents (Claude Code,
OpenCode, or any similar tool) can navigate and answer questions effectively
without a custom query pipeline.

### Navigation Layer

The vault includes a layered navigation system:

1. **`AGENTS.md`** — the operating manual (read first)
2. **`wiki/indexes/START_HERE.md`** — orientation map with vault stats and routing
3. **`wiki/indexes/QUERY_PROTOCOL.md`** — step-by-step query procedure
4. **`wiki/indexes/INDEX.md`** — full vault index with stats and recent sources
5. **`wiki/indexes/TOPICS.md`** — topic pages with source counts
6. **`wiki/indexes/ENTITIES.md`** — entity pages with types and source counts
7. **`wiki/indexes/CONCEPTS.md`** — concept pages with source counts

### Agent Skills

Optional skill files improve agent consistency:

- **`.claude/skills/vault-query.md`** — Claude Code query skill
- **`.opencode/VAULT_QUERY.md`** — OpenCode agent instructions

These are loaded automatically when the agent operates on the vault directory.
The vault works well even without these skills — the navigation files and
`AGENTS.md` are sufficient for good results.

### Why Agent-First

The previous `epistora query` command used a snippet-based search + LLM generation
pipeline that was weaker than what a capable agent can do by directly reading
vault files. Direct agent access allows:

- Reading full source notes, not just snippets
- Following wikilinks as a knowledge graph
- Checking frontmatter for metadata before reading bodies
- Escalating to raw captures when needed
- Producing structured, source-grounded answers with note references

The query graph code is retained for backward compatibility but deprecated.
