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

Responsible for fetching source metadata and content.

- **`classifier.py`** — Determines `SourceType` from a URL using regex patterns
- **`raindrop.py`** — `RaindropConnector` calls the Raindrop.io API to fetch saved bookmarks
- **`fetchers/`** — Content extraction by type:
  - `article.py` — Uses trafilatura for readable article extraction
  - `youtube.py` — Fetches transcripts via `youtube-transcript-api`
  - `x_thread.py` — Best-effort X/Twitter extraction via noembed + page scraping
  - `pdf.py` — PDF text extraction using PyMuPDF
  - `generic.py` — Fallback using trafilatura on any URL

**Extensibility:** New connectors implement the same pattern: receive a `SourceItem`, return a `SourceContent`. Adding a `ReadwiseReaderConnector` or `RSSConnector` requires only a new file and registering it in the fetcher dispatcher.

### B. Normalization Layer (`app/models/`)

All data flows through typed Pydantic models:

- **`source.py`** — `SourceItem` (pre-fetch metadata), `SourceContent` (post-fetch normalized content), `SourceType` enum
- **`knowledge.py`** — `Topic`, `Entity`, `Concept`, `SynthesisNote`
- **`results.py`** — `IngestResult`, `QueryResult`, `LintResult`, `VaultUpdate`, `LintIssue`
- **`db.py`** — `ProcessedSource`, `SyncCursor`, `VaultNoteMapping` (SQLite row models)

### C. Backend Layer (`app/backends/`)

The backend layer abstracts over multiple reasoning/LLM execution engines so the rest of the app is backend-agnostic.

#### Design

```
ReasoningBackend (abstract base)
  ├── DirectApiBackend      – OpenAI-compatible API calls via LangChain
  ├── OpenCodeCliBackend    – Shells out to `opencode run`
  └── ClaudeCodeCliBackend  – Shells out to `claude -p`

BackendRouter
  - Holds a registry of backends keyed by BackendType
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
Each node is an async function that transforms the shared `IngestState`. The LLM is called during `analyse` via `run_structured()` — the backend router picks the appropriate backend for the "ingest" task.

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
- **`templates.py`** — Markdown + YAML frontmatter generators for each note type
- **`writer.py`** — `VaultWriter` handles create-or-update logic, including merging source lists
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
3. Dedup check against URL hash / content hash in SQLite
4. Backend router selects best available backend for "ingest" task
5. LLM generates structured analysis (summary, takeaways, topics, entities, concepts)
6. Knowledge extraction produces `Topic`, `Entity`, `Concept` models
7. VaultWriter creates/updates:
   - Raw capture → `inbox/raw/{type}/`
   - Source note → `wiki/sources/{type}/`
   - Topic pages → `wiki/topics/`
   - Entity pages → `wiki/entities/`
   - Concept pages → `wiki/concepts/`
8. Indexes rebuilt, ingest log appended, SQLite state updated

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
