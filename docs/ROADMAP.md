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
- [x] Reset command for generated vault/state replay
- [x] Expanded tests for raw/source separation, article-tag routing, and reset flow

## v1.5 — Polish & Enrichment

- [ ] Readwise Reader connector
- [ ] RSS feed connector
- [ ] Local folder watcher (ingest markdown/PDF files dropped into a folder)
- [ ] Weekly digest command (`kb digest`)
- [ ] Improved topic page synthesis (deeper multi-source writing, contradictions, and learning paths)
- [ ] Git integration for vault versioning
- [ ] Simple HTML status dashboard
- [ ] Configurable prompt templates
- [ ] Batch ingest from URL list / OPML file
- [ ] X thread stitching and article expansion quality improvements
- [ ] Cron expression support for the scheduler
- [ ] Ollama / local model backend

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
