# Epistora — Build Plan

## Overview

Build a local-first personal knowledge compiler that turns saved links (from Raindrop.io and direct URLs) into a persistent, markdown-based, queryable knowledge base compatible with Obsidian.

## Implementation Phases

### Phase 1: Foundation ✅
- [x] Project scaffold and dependencies
- [x] Pydantic models (SourceItem, SourceContent, Topic, Entity, Concept, etc.)
- [x] Configuration and settings
- [x] SQLite storage layer
- [x] Utility functions (hashing, slugify, markdown, dates)

### Phase 2: Vault Layer ✅
- [x] Vault directory structure and path helpers
- [x] Markdown note templates (source, topic, entity, concept, synthesis)
- [x] VaultWriter with create/update logic
- [x] Vault parser for reading notes
- [x] Index rebuilder
- [x] Log updater (ingest log, lint log)
- [x] AGENTS.md conventions file

### Phase 3: Connectors ✅
- [x] URL classifier (YouTube, X, PDF, article)
- [x] Raindrop.io connector
- [x] Article fetcher (trafilatura)
- [x] YouTube transcript fetcher
- [x] X/Twitter best-effort fetcher
- [x] PDF text extractor (PyMuPDF)
- [x] Generic fallback fetcher

### Phase 4: Compiler / Orchestrator ✅
- [x] LLM client setup (LangChain + OpenAI)
- [x] Prompt templates
- [x] Ingest LangGraph workflow (fetch → dedup → analyse → extract → write → persist)
- [x] Query LangGraph workflow (resolve → generate → save)
- [x] Lint LangGraph workflow (scan → structural → llm → report)

### Phase 5: Retrieval ✅
- [x] FTS5 search index over vault markdown
- [x] Keyword fallback search
- [x] Name-to-page resolver

### Phase 6: Interfaces ✅
- [x] Typer CLI (init, ingest-url, sync-raindrop, query, lint, status, rebuild-indexes)
- [x] FastAPI API (health, ingest, query, lint, status, indexes)

### Phase 7: Quality ✅
- [x] Tests for classifier, vault writer, ingest flow, query flow, lint flow
- [x] Documentation (README, ARCHITECTURE, PLAN, ROADMAP)

### Phase 8: Multi-Backend & Automation ✅
- [x] Backend abstraction layer (`app/backends/`)
  - [x] `ReasoningBackend` abstract base class with `generate`, `generate_structured`, `is_available`, `describe`
  - [x] `DirectApiBackend` — OpenAI-compatible API with per-task overrides
  - [x] `OpenCodeCliBackend` — subprocess execution with timeout and JSON parsing
  - [x] `ClaudeCodeCliBackend` — subprocess execution in print mode
  - [x] `BackendRouter` — per-task fallback with both selection-time and execution-time fallback
  - [x] `BackendRequest` / `BackendResponse` / `BackendDescriptor` models
- [x] Extended `Settings` with 50+ configuration fields for all backends and automation
- [x] Refactored `compiler/llm.py` to expose `get_backend_router()`, `run_text()`, `run_structured()`
- [x] Updated all three graph files to use the backend router instead of `get_llm()` directly
- [x] Automation subsystem (`app/automation/`)
  - [x] `IntervalScheduler` with `ScheduledJob` management
  - [x] `FileLock` using fcntl for process-level exclusion
  - [x] Job definitions for sync, lint, and index rebuild
  - [x] `run_worker()` main loop with graceful shutdown
- [x] New CLI commands: `worker`, `backend-status`, `run-sync`, `run-lint`
- [x] Automation API endpoints: `/automation/status`, `/automation/run-sync`, `/automation/run-lint`, `/automation/rebuild-indexes`
- [x] Tests for backend availability, routing, fallback, JSON parsing, automation scheduler, locks, jobs
- [x] Integration tests with mocked backend router for all three graph workflows
- [x] Updated all documentation

### Phase 9: Extraction Stack Upgrade ✅
- [x] Extend `SourceContent` model with extraction metadata (method, fallback_chain, raw_metadata, canonical_url)
- [x] Add `ExtractionQuality` enum (full, mostly_full, partial, metadata_only, failed)
- [x] Extraction config settings (article, YouTube, X, browser timeouts and toggles)
- [x] Quality scoring utilities (`app/utils/extraction.py`)
- [x] Article fetcher: Trafilatura → readability-lxml → browser rendering → metadata-only
- [x] YouTube fetcher: transcript-api → yt-dlp subtitles → metadata/noembed + ASR hook
- [x] X fetcher overhaul: Official API → fxtwitter/vxtwitter → oEmbed → page scrape → browser
  - [x] `x_api.py` — Official X API v2 client with thread reconstruction
  - [x] `x_mirrors.py` — fxtwitter/vxtwitter/oEmbed helpers
  - [x] Five-tier fallback in `x_thread.py`
- [x] Generic fetcher: Trafilatura → readability → browser → metadata-only
- [x] PDF fetcher: Updated with extraction metadata
- [x] Browser fallback module (`browser.py`) — optional Playwright
- [x] Readability module (`readability.py`) — readability-lxml wrapper
- [x] Fetcher router with timing, logging, and crash protection
- [x] Vault templates updated with extraction_method, fallback_chain, canonical_url
- [x] New dependency: `readability-lxml`; optional: `playwright`
- [x] Tests: 41 new tests covering all fetcher fallback chains and quality scoring
- [x] Documentation updates (README, ARCHITECTURE, ROADMAP)

## Key Decisions

1. **LangGraph over raw LangChain chains**: Gives clear state machines for each workflow, easy to extend with new nodes
2. **FTS5 for search**: Zero infrastructure, ships with SQLite, good enough for v1
3. **trafilatura for article extraction**: Best-in-class Python readability extraction
4. **PyMuPDF for PDFs**: Fast, reliable, no Java dependencies
5. **Immutable raw captures**: Provenance-first design, can always re-process
6. **Backend abstraction via protocol**: Keeps LangGraph nodes backend-agnostic; new providers only need one file
7. **CLI backends**: Enables using OpenCode/Claude Code without reimplementing their auth/model access
8. **File-based locking**: Simplest reliable mechanism for single-machine local-first automation
9. **Interval scheduler over cron**: Simpler implementation, adequate for the use case, cron can be added later
10. **Multi-tier extraction fallbacks**: Each source type has its own fallback chain to maximize content capture while degrading gracefully
11. **X API optional, mirrors default**: Official X API provides best quality but free mirrors (fxtwitter/vxtwitter) work well enough as default
12. **Browser rendering opt-in**: Playwright adds significant weight; kept as optional install with config toggle

### Phase 10: Knowledge Compiler Quality Upgrade
- [ ] Resolve current branch instability in vault templates and keep all user-owned edits intact
- [ ] Upgrade the source-analysis schema and prompts so source notes are richer, more grounded, and more cumulative
- [ ] Improve YouTube ingest:
  - [ ] Preserve transcript/raw capture separately from compiled notes
  - [ ] Clean transcript structure and record transcript availability / quality
  - [ ] Generate article-style video notes with a 5-minute read and detailed reading version
- [ ] Improve article ingest for Raindrop items tagged `article`:
  - [ ] Treat the tag as a strong signal to use article extraction
  - [ ] Preserve a clean readable markdown archive in the raw layer
  - [ ] Keep the compiled source note separate from the raw archive
- [ ] Strengthen vault templates and conventions:
  - [ ] Source note templates for video/article/generic sources
  - [ ] Topic/entity/concept/synthesis templates with stronger navigation sections
  - [ ] `knowledge_vault_template/AGENTS.md` as the operating manual for the vault
- [ ] Improve maintenance surfaces:
  - [ ] Query prompt and saved outputs for better grounded answers
  - [ ] Lint prompt and structural checks for wiki health issues
  - [ ] Index and ingest-log generation so the vault is easier to navigate
- [ ] Add a clean reset path for generated vault artifacts and internal generated state
- [ ] Re-run the upgraded pipeline against the latest 30 Raindrop bookmarks from a clean state
- [ ] Inspect generated results, fix workflow or quality issues discovered during the rerun, and rerun as needed
- [ ] Expand tests for YouTube/article raw-vs-compiled separation and mixed-source ingest
- [ ] Update README and architecture/development/roadmap docs with the new behavior and validation notes
