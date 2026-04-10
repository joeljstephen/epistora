# Read Model Foundation

This document describes the v2 read-model retrieval foundation.

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
- self-contained as the only runtime retrieval database

## What It Stores

The read model stores:

- note catalog rows
- note type metadata
- bounded note body excerpts for retrieval context
- frontmatter-derived topic/entity/concept associations
- typed relationship edges
- integrated lexical search rows
- per-note `indexed_at` and file mtime
- global refresh state such as schema migration time, last full rebuild, and last incremental refresh

## Current Schema Shape

Main tables:

- `read_model_notes`
- `read_model_edges`
- `read_model_fts`
- `read_model_state`

Relationship types currently included:

- `topic_membership`
- `entity_mention`
- `concept_relationship`
- `backlink`
- `source_support`
- `derived_from`

## Refresh Strategy

The markdown sink now refreshes the read model after publishing canonical artifacts.

Current behavior:

- changed note paths are refreshed incrementally where possible
- index files rebuilt by the markdown sink are also refreshed into the catalog
- if a changed note title changes, the store falls back to a full rebuild because title-based link resolution may affect other notes

Lexical search is part of this same read-model database. The old standalone
`search.db` path has been retired.

## Query Helpers

The read-model store now provides the retrieval/query substrate for:

- listing notes
- fetching a note record
- fetching edges by source/target/relation type
- fetching backlinks as inverse edge queries
- fetching related edges for a source note
- structured candidate resolution
- lexical support search inside the read model
- excerpt generation for query context

## Intentionally Not Done

Phase 3 does not add:

- a graph database
- vector retrieval
- advanced ranking or reranking
- cross-machine shared database assumptions
- a full replacement for direct filesystem agent navigation

Direct agent use of the vault remains fully valid even if the read model is absent or stale.
