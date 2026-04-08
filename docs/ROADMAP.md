# Epistora — Roadmap

## v1.0 — Foundation ✅

- [x] CLI and API interfaces
- [x] Raindrop.io connector
- [x] Article, YouTube, X/Twitter, PDF, and generic content extraction
- [x] LangGraph-based ingest, query, and lint workflows
- [x] Markdown vault with YAML frontmatter and wikilinks
- [x] FTS5 search index
- [x] Deduplication by URL and content hash
- [x] Vault indexes and operational logs
- [x] SQLite internal state tracking

## v1.1 — Multi-Backend & Automation ✅

- [x] Backend abstraction layer (ReasoningBackend protocol)
- [x] Direct API backend (OpenAI-compatible, configurable base_url)
- [x] OpenCode CLI backend
- [x] Claude Code CLI backend
- [x] Backend router with per-task fallback ordering
- [x] Per-task model/backend configuration
- [x] Automatic fallback with clear logging
- [x] Background automation worker (`kb worker`)
- [x] Interval-based scheduler for sync, lint, and index rebuild
- [x] File-based locking for overlap prevention
- [x] Automation API endpoints
- [x] Backend availability checks and status command
- [x] Tests for backend routing, availability, and automation
- [x] Updated documentation and configuration

## v1.2 — Extraction Stack Upgrade ✅

- [x] Multi-tier fallback chains for all source types
- [x] Article: Trafilatura → readability-lxml → browser rendering → metadata-only
- [x] YouTube: transcript-api → yt-dlp subtitles → metadata/noembed + ASR hook point
- [x] X/Twitter: Official API → fxtwitter/vxtwitter → oEmbed → page scrape → browser
- [x] Structured extraction quality scoring (full/mostly_full/partial/metadata_only/failed)
- [x] Extraction metadata on every result (method, fallback chain, notes, raw metadata)
- [x] Canonical URL resolution
- [x] Optional browser-rendered fallback via Playwright
- [x] Optional official X API support (works without it via free mirrors)
- [x] yt-dlp subtitle-only fallback for YouTube
- [x] readability-lxml fallback for articles and generic pages
- [x] OG metadata extraction and page scraping helpers
- [x] Comprehensive tests for all fetcher fallback chains
- [x] Extraction config settings (timeouts, feature toggles)
- [x] Updated vault note templates with extraction metadata

## v1.3 — Knowledge Compiler Quality Upgrade ✅

- [x] Richer source-analysis prompt/schema for persistent wiki notes
- [x] YouTube transcript preservation plus article-style source notes
- [x] Clean readable raw article markdown archives in the raw layer
- [x] Explicit raw-vs-compiled separation in source note templates
- [x] Stronger topic/entity/concept templates and vault operating manual
- [x] More navigable indexes and richer ingest logs
- [x] Force re-ingest path without deleting existing vault state
- [x] Name normalization against existing topic/entity/concept pages
- [x] Validation on the latest Raindrop bookmark without resetting generated documents
- [x] Reset command for generated vault/state replay
- [x] Expanded tests for raw/source separation, article-tag routing, and reset flow

## v1.4 — Agent-First Query Model ✅

- [x] Deprecated `kb query` CLI command and `/query` API endpoint
- [x] Rewrote `AGENTS.md` as a comprehensive agent operating manual
- [x] Added `wiki/indexes/START_HERE.md` — vault orientation map
- [x] Added `wiki/indexes/QUERY_PROTOCOL.md` — standard agent query procedure
- [x] Auto-generated START_HERE and QUERY_PROTOCOL during index rebuilds
- [x] Added `.claude/skills/vault-query.md` — Claude Code query skill
- [x] Added `.opencode/VAULT_QUERY.md` — OpenCode agent instructions
- [x] Updated all documentation for agent-first workflow
- [x] Updated README with Claude Code / OpenCode usage sections
- [x] Updated tests for new navigation files and deprecation warnings

## v1.4.1 — summarize.sh Extraction Integration ✅

- [x] Dedicated `summarize_cli.py` wrapper with availability checks, timeout handling, and JSON parsing
- [x] `SourceContent`-boundary normalization for summarize output
- [x] YouTube summarize-first extraction with safe fallback to the existing local stack
- [x] Article summarize fallback after Trafilatura/readability
- [x] Generic summarize fallback after the generic extractor
- [x] X summarize fallback only after X-specific API/mirror/oEmbed tiers
- [x] Explicit weak-extraction heuristics and extraction-method/fallback reporting
- [x] Focused wrapper and fetcher integration tests
- [x] Documentation for setup, precedence order, and debugging

## v1.5 — Queue-Based Cross-Platform Automation ✅

- [x] Durable SQLite queue separating discovery from processing
- [x] Safe / balanced / deep automation modes with cost control
- [x] One-shot `kb automation run-pending` command for scheduler integration
- [x] Discovery pipeline: fetch bookmarks → stage in queue → advance cursor only after staging
- [x] Processing pipeline: mode-aware enrichment with failure classification and exponential backoff
- [x] Partial batch failure handling (one failed item doesn't block the rest)
- [x] Retryable vs permanent failure tracking with max attempt caps
- [x] Cross-platform scheduler helper generation (macOS LaunchAgent, Linux systemd, Windows Task Scheduler)
- [x] Automation status and observability (`kb automation status`)
- [x] Queue management commands (list-pending, retry-failed)
- [x] Automation run history table for observability
- [x] Per-item attempt history for debugging
- [x] Daily enrichment caps to prevent runaway LLM costs
- [x] 39 new tests covering queue, discovery, processing, runner, modes, and scheduler helpers
- [x] Updated API endpoints for queue-based automation
- [x] Extended config with 15+ automation settings
- [x] Updated all documentation

## v1.6 — Polish & Enrichment

- [ ] Readwise Reader connector
- [ ] RSS feed connector
- [ ] Local folder watcher (ingest markdown/PDF files dropped into a folder)
- [ ] Weekly digest command (`kb digest`)
- [ ] Improved topic page synthesis (deeper multi-source writing, contradictions, and learning paths)
- [ ] Stronger semantic dedup for near-duplicate topics that are related but not simple spelling variants
- [ ] Git integration for vault versioning
- [ ] Simple HTML status dashboard
- [ ] Configurable prompt templates
- [ ] Batch ingest from URL list / OPML file
- [ ] X thread stitching and article expansion quality improvements
- [ ] Cron expression support for the scheduler
- [ ] Ollama / local model backend
- [ ] Reuse summarize first-pass summaries as additional `analyse` evidence without changing Epistora's schema
- [ ] Optional summarize daemon support
- [ ] More media-specific extraction paths beyond YouTube

## v2.0 — Productization

- [ ] Notion as an alternative destination (write knowledge pages to Notion)
- [ ] Semantic search with local embeddings (sentence-transformers)
- [ ] Graph visualization of knowledge connections
- [ ] Multi-vault support
- [ ] Plugin system for custom connectors and processors
- [ ] Export to Anki flashcards from key takeaways
- [ ] Conflict resolution UI for lint issues
- [ ] Collaborative vaults (shared knowledge bases)

## v3.0 — Intelligence Layer

- [ ] Automatic learning path generation from vault contents
- [ ] Spaced repetition integration
- [ ] Cross-vault knowledge federation
- [ ] Custom fine-tuned models for domain-specific knowledge compilation
- [ ] Agent-based research flows (auto-discover and ingest related sources)
