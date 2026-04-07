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

## Key Decisions

1. **LangGraph over raw LangChain chains**: Gives clear state machines for each workflow, easy to extend with new nodes
2. **FTS5 for search**: Zero infrastructure, ships with SQLite, good enough for v1
3. **trafilatura for article extraction**: Best-in-class Python readability extraction
4. **PyMuPDF for PDFs**: Fast, reliable, no Java dependencies
5. **Immutable raw captures**: Provenance-first design, can always re-process
