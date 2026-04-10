# Read Model Foundation

This document describes the Phase 3 read-model foundation.

## Role

The read model is a derived local helper layer. It improves navigation and query support, but it does not replace vault files as the source of truth.

The current boundary is:

```text
vault files -> read model refresh/rebuild -> derived SQLite helper DB
```

## Storage

The read model currently lives at:

- `.system/state/read_model.db`

This keeps it:

- local-first
- rebuildable from files
- separate from the operational ingest ledger
- separate from the FTS search database

## What It Stores

Phase 3 stores:

- note catalog rows
- note type metadata
- frontmatter-derived topic/entity/concept associations
- wikilink edges
- source-to-topic/entity/concept edges
- backlink-equivalent incoming edge queries
- per-note `indexed_at` and file mtime
- global refresh state such as last full rebuild and last incremental refresh

## Current Schema Shape

Main tables:

- `read_model_notes`
- `read_model_edges`
- `read_model_state`

Relationship types currently included:

- `wikilink`
- `source_topic`
- `source_entity`
- `source_concept`

## Refresh Strategy

The markdown sink now refreshes the read model after publishing canonical artifacts.

Current behavior:

- changed note paths are refreshed incrementally where possible
- index files rebuilt by the markdown sink are also refreshed into the catalog
- if a changed note title changes, the store falls back to a full rebuild because title-based link resolution may affect other notes

This keeps the implementation simple and safe without introducing a graph database or heavy indexing platform.

## Query Helpers

The current read-model store provides internal helper methods for:

- listing notes
- fetching a note record
- fetching edges by source/target/relation type
- fetching backlinks as inverse edge queries
- fetching related edges for a source note

These helpers are foundation-level utilities, not a full query product.

## Intentionally Not Done

Phase 3 does not add:

- a graph database
- vector retrieval
- advanced ranking or reranking
- cross-machine shared database assumptions
- a full replacement for direct filesystem agent navigation

Direct agent use of the vault remains fully valid even if the read model is absent or stale.
