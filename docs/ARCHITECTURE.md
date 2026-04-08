# Epistora — Architecture

## System Overview

Epistora is a local-first personal knowledge compiler. It ingests content from saved links, compiles structured knowledge notes, and maintains a queryable Obsidian-compatible vault.

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Sources    │     │   Compiler   │     │    Vault     │
│              │────▶│  (LangGraph) │────▶│  (Markdown)  │
│ Raindrop     │     │              │     │              │
│ Direct URLs  │     │ Ingest Graph │     │ Source Notes │
│              │     │ Query Graph  │     │ Topic Pages  │
│              │     │ Lint Graph   │     │ Entity Pages │
└──────────────┘     └──────┬───────┘     │ Concept Pages│
                            │             │ Indexes/Logs │
                     ┌──────▼───────┐     └──────────────┘
                     │Backend Router│
                     │              │
                     │ API │OC│ CC  │
                     └──────────────┘
                            │
                     ┌──────▼───────┐
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
  - `article.py` — Trafilatura → readability-lxml → browser rendering → metadata-only, plus a clean archived article markdown output
  - `youtube.py` — youtube-transcript-api → yt-dlp subtitles → metadata/noembed → ASR hook, plus structured transcript capture
  - `x_thread.py` — Official X API → fxtwitter/vxtwitter → oEmbed/noembed → page scrape → browser
  - `pdf.py` — PyMuPDF text extraction with PDF metadata
  - `generic.py` — Trafilatura → readability → browser → metadata-only
  - `browser.py` — Optional Playwright-based rendered extraction (shared by other fetchers)
  - `readability.py` — readability-lxml wrapper (shared by article + generic)
  - `x_api.py` — Official X API v2 client for post/thread extraction
  - `x_mirrors.py` — fxtwitter/vxtwitter/oEmbed helpers for free X extraction
- **`utils/extraction.py`** — Shared helpers: quality scoring, OG metadata, URL canonicalization

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

#### X/Twitter Extraction Strategy

X extraction uses a five-tier fallback:

1. **Official X API** (Tier 1): When `X_API_BEARER_TOKEN` is configured, uses the Twitter v2 API for full post text, thread reconstruction via `conversation_id`, and structured metadata. Optional — never required.
2. **Free mirror APIs** (Tier 2): fxtwitter and vxtwitter provide full tweet text, thread content, and X article expansion via free public endpoints.
3. **oEmbed** (Tier 3): Twitter oEmbed and noembed for basic tweet text.
4. **Page scrape** (Tier 4): Direct OG metadata extraction.
5. **Browser rendering** (Tier 5): Optional Playwright-based fallback for difficult cases.

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

#### Query Graph
```
resolve_context → generate_answer → maybe_save
```
Searches the vault for relevant notes, builds context, and generates a grounded answer via `run_text()` using the "query" task backend.

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

The automation subsystem enables hands-free operation:

- **`worker.py`** — Main loop for `kb worker`. Acquires a file lock, builds a scheduler, and ticks every 5s until interrupted.
- **`scheduler.py`** — `IntervalScheduler` manages `ScheduledJob` instances. Each job has an interval, an async function, and overlap protection.
- **`jobs.py`** — Individual job functions (`run_sync_job`, `run_lint_job`, `run_rebuild_indexes_job`) that call the existing service layer.
- **`locks.py`** — `FileLock` using `fcntl.flock` for single-machine mutual exclusion.

### I. Interface Layer

- **CLI** (`app/cli/main.py`) — Typer-based, primary operator interface
- **API** (`app/main.py` + `app/api/`) — FastAPI with OpenAPI docs

## Data Flow: Ingest

1. User runs `kb ingest-url <url>` or `POST /ingest/url`
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

- `kb ingest-url --force <url>`
- `kb sync-inbox --force`
- `kb sync-raindrop --force`

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
