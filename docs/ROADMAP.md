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

## v1.5 — Polish & Enrichment

- [ ] Readwise Reader connector
- [ ] RSS feed connector
- [ ] Local folder watcher (ingest markdown/PDF files dropped into a folder)
- [ ] Weekly digest command (`kb digest`)
- [ ] Improved topic page synthesis (merge patterns across sources)
- [ ] Git integration for vault versioning
- [ ] Simple HTML status dashboard
- [ ] Configurable prompt templates
- [ ] Batch ingest from URL list / OPML file
- [ ] Better X/Twitter extraction with API authentication option
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
