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
└──────────────┘     └──────────────┘     │ Concept Pages│
                                          │ Indexes/Logs │
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

### C. Compiler/Orchestrator Layer (`app/compiler/`)

Uses LangGraph state machines for the three core workflows:

#### Ingest Graph
```
fetch → dedup → analyse → extract_knowledge → write_vault → persist
```
Each node is an async function that transforms the shared `IngestState`. The LLM is called during `analyse` to produce structured summaries and extract topics/entities/concepts.

#### Query Graph
```
resolve_context → generate_answer → maybe_save
```
Searches the vault for relevant notes, builds context, and generates a grounded answer.

#### Lint Graph
```
scan_vault → structural_lint → llm_lint → generate_report
```
Combines rule-based checks (orphans, backlinks, weak pages) with LLM-powered semantic analysis (contradictions, duplicates).

### D. Vault Writer Layer (`app/vault/`)

- **`paths.py`** — All vault path conventions in one place
- **`templates.py`** — Markdown + YAML frontmatter generators for each note type
- **`writer.py`** — `VaultWriter` handles create-or-update logic, including merging source lists
- **`parser.py`** — `VaultNote` class for reading and introspecting existing notes
- **`index_updater.py`** — Rebuilds INDEX, TOPICS, ENTITIES, CONCEPTS indexes
- **`log_updater.py`** — Appends to ingest log, writes lint reports

### E. Retrieval Layer (`app/retrieval/`)

- **`indexer.py`** — SQLite FTS5 full-text search index over vault markdown
- **`search.py`** — Combined FTS + keyword fallback search
- **`resolver.py`** — Maps names to existing vault pages by slug

### F. Storage Layer (`app/storage/`)

- **`sqlite.py`** — `Database` class with WAL mode and schema auto-migration
- **`repositories.py`** — Repository pattern for processed sources, sync cursors, vault note mappings

### G. Interface Layer

- **CLI** (`app/cli/main.py`) — Typer-based, primary operator interface
- **API** (`app/main.py` + `app/api/`) — FastAPI with OpenAPI docs

## Data Flow: Ingest

1. User runs `kb ingest-url <url>` or `POST /ingest/url`
2. URL classified → appropriate fetcher called → `SourceContent` produced
3. Dedup check against URL hash / content hash in SQLite
4. LLM generates structured analysis (summary, takeaways, topics, entities, concepts)
5. Knowledge extraction produces `Topic`, `Entity`, `Concept` models
6. VaultWriter creates/updates:
   - Raw capture → `inbox/raw/{type}/`
   - Source note → `wiki/sources/{type}/`
   - Topic pages → `wiki/topics/`
   - Entity pages → `wiki/entities/`
   - Concept pages → `wiki/concepts/`
7. Indexes rebuilt, ingest log appended, SQLite state updated

## Future Extensibility

Adding a new source connector (e.g., Readwise Reader):

1. Create `app/connectors/readwise.py` implementing fetch methods
2. Register in `app/connectors/fetchers/__init__.py` if it provides a content fetcher
3. Add a sync command to CLI and API route
4. All downstream processing (compile, write, index) works unchanged

Adding a new destination (e.g., Notion):

1. Create a destination writer alongside `VaultWriter`
2. The same `IngestResult` model feeds both vault and Notion outputs
3. Core compiler logic is destination-agnostic
