# Epistora Roadmap

This roadmap tracks the current product direction. Historical implementation
plans and audit snapshots were removed from `docs/`; `ARCHITECTURE.md` is the
canonical description of the implemented system.

## Implemented Foundation

- Local-first markdown vault with immutable raw evidence, source notes, hubs,
  indexes, logs, and generated outputs.
- Raindrop inbox connector plus direct URL ingest.
- Article, YouTube, X/Twitter, PDF, and generic extraction paths with fallback
  chains and extraction-quality metadata.
- Canonical `ArtifactBundle` compiler boundary before sink publishing.
- Markdown vault sink by default and optional deterministic JSON export sink.
- Read-model-native built-in retrieval backed by `.system/state/read_model.db`.
- Queue-based automation with `safe`, `balanced`, and `deep` execution-depth
  policies.
- Prompt composition with built-in prompts, plugin prompt packs, workspace
  prompt guidance, prompt profiles, and user overrides.
- Plugin manifest discovery for inbox providers, reasoning backends, sinks, and
  prompt packs.
- Bounded maintenance planning for structure, hubs, backlinks, candidate
  synthesis, and read-model refresh.
- Personal Learning Mode as a composed preset with reader views, topic bundles,
  daily/weekly review digests, and a `personal_learning` prompt profile.

## Near-Term Priorities

- Improve the brief-first source-note experience for non-YouTube sources.
- Expand deterministic theme-tag mappings beyond the current small allowed set.
- Harden personal-learning review thresholds with more real-vault examples.
- Add focused golden-path tests for YouTube briefs, topic bundles, and review
  digests.
- Decide whether to retire the legacy interval worker now that the queue-first
  runner is the recommended automation path.
- Replace the markdown sink compatibility bridge with direct artifact-to-note
  rendering when the risk is worth the cleanup.

## Later Work

- Additional inbox connectors such as Readwise Reader, RSS, and local folder
  watch ingestion.
- Better semantic deduplication for related topics and near-duplicate concepts.
- Local embedding-backed retrieval or reranking as an optional helper, without
  replacing direct vault navigation.
- More media-specific extraction paths beyond YouTube.
- Git-based vault versioning helpers.
- Optional export targets such as Notion or static sites.
- Advanced review and spaced-repetition flows built on top of review history
  rather than replacing the current digest model.
