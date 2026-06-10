# Roadmap

This roadmap tracks active direction only. Historical implementation plans have
been removed from `docs/`; durable decisions belong in `docs/adr/`.

## Implemented Foundation

- Local-first markdown vault with raw evidence, compiled source notes, hub
  pages, generated outputs, logs, and index views.
- Direct URL ingest plus Raindrop and Readwise connector flows.
- Readwise import as an extracted-content path that can avoid LLM calls until
  brief compilation.
- Article, YouTube, X/Twitter, PDF, and generic extraction paths with fallback
  metadata.
- Rich source brief path feeding canonical `ArtifactBundle` construction.
- Markdown vault sink by default and optional deterministic JSON export sink.
- Evidence storage tiers with blob-backed large raw captures.
- Source catalog, provider refs, tags, source-linked jobs, attempts, usage
  events, and catalog snapshots in SQLite.
- Derived read model for built-in retrieval and Studio knowledge/search views.
- Local Studio served by FastAPI with Library, Search, Queue, Settings, source
  reader pages, Readwise sync, brief compilation, snapshots, and chat.
- Sidebar and broad Studio chat with persisted broad conversations and chat
  settings.
- Queue automation with `safe`, `balanced`, and `deep` modes.
- Personal-learning workflow preset with reader views, topic bundles, and
  daily/weekly review digests.
- Prompt layering with built-in prompts, prompt packs, profiles, vault-local
  overrides, and backend/model hints.
- Plugin manifest discovery for prompt packs, providers, backends, and sinks.
- Bounded maintenance planning for structure, hubs, backlinks, candidate
  synthesis, read-model refresh, and search refresh.

## Near-Term Priorities

- Polish the Readwise-to-vault loop: import quality, brief rendering, Studio
  controls, and force re-briefing behavior.
- Improve source brief consistency across articles, YouTube, threads, PDFs, and
  generic pages.
- Harden Studio chat references and tool-call rendering against real vaults.
- Improve catalog snapshot recovery and operator messaging.
- Add more focused golden tests for source briefs, Studio flows, and chat.
- Reduce compatibility bridges where direct artifact-to-note rendering is now
  mature enough.
- Decide whether to retire the legacy interval worker in favor of queue-only
  automation.

## Later Work

- Additional inbox connectors such as RSS, local folder watch, or more Reader
  providers.
- Stronger semantic deduplication for near-duplicate sources and hub pages.
- Optional embedding-backed retrieval or reranking without replacing direct
  vault navigation.
- More media-specific extraction paths.
- Git-based vault versioning helpers.
- Additional export targets beyond markdown and JSON.
- Deeper spaced-repetition and review workflows based on review history.
