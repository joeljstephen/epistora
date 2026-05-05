# Local Studio Architecture Decisions

Status: accepted direction for the first Local Studio implementation.

Implementation note: the first foundation slice has landed for the source
catalog schema and repository layer. Raindrop discovery can now create
metadata-only source rows, provider references, normalized provider tags, and
deterministic priority scores without fetching content or publishing vault
notes. Studio APIs and frontend routes remain deferred.

Implementation note: the backend/API slice now exposes source-catalog-first
Studio routes for listing/searching sources, source detail, manual URL add,
source action enqueueing, bounded one-shot processing of source-linked jobs,
and JSONL catalog snapshot export/import. The frontend remains deferred.

Implementation note: the first UI slice now lives under `studio/static/` and
is served by FastAPI at `GET /studio`. `epistora studio` starts the local API,
serves Library, Search, Queue, Settings, Source Detail, manual URL add, source
actions, job processing, and snapshot controls against the implemented Studio
APIs. Advanced pages remain deferred.

Implementation note: the Studio UI/reader has been revamped into a reader-first
editorial environment. The frontend now ships as a React + Vite app under
`studio/`, with production assets built into `studio/static/` and loaded by
FastAPI from `/studio/assets/*`. New UI surfaces:

- Library sections: All sources, Articles, Videos / YouTube, Threads,
  Documents, Metadata only, Brief ready, Deep compiled, Needs attention.
  Sections are filters over `GET /studio/sources` using new query params
  (`source_type`, `display_state`, `provider`, `tag`).
- Source Detail is now a full reader page with Compiled note, Raw capture,
  Metadata, and Jobs tabs. Markdown rendering covers headings, paragraphs,
  unordered/ordered/nested lists, blockquotes, fenced code blocks (with
  language hints), inline code, links, wikilinks, horizontal rules, tables,
  and frontmatter parsing/hiding.
- Knowledge browse (read-only): Topics, Entities, Concepts, Synthesis. Backed
  by `GET /studio/knowledge/{note_type}` over the existing read model and a
  vault-scan fallback when the read model is empty.
- Search now uses `GET /studio/search`, combining catalog matches and read-model
  notes with explicit `provenance` fields (`catalog`, `metadata_only`,
  `read_model`, `vault`).
- Queue jobs include `source_title`, `source_url`, `source_type`, and
  `attempt_count` and the queue UI offers status filter chips (queued, running,
  completed, failed). One-shot job processing remains the only execution path;
  no persistent worker.
- Settings shows runtime info plus a catalog snapshot panel built from the new
  `GET /studio/stats` endpoint.

The reader is intentionally not driven by JSON export shape. `GET
/studio/sources/{source_uid}/reader` now returns parsed frontmatter and body
text alongside the original markdown, so the frontend can render compiled and
raw notes while keeping vault files as the durable artifact.

This document records the agreed Local Studio decisions that extend the current
Epistora architecture. It is intentionally more specific than the roadmap, but
less final than implementation DDL. Exact column names and migrations may change
as code lands.

## Product Boundary

Epistora Local Studio is a local web UI and local API on top of the existing
core. It must not replace the markdown vault, JSON export sink, read model,
artifact compiler, or queue automation.

The guiding rule is:

```text
Import everything. Index everything. Enrich selectively. Deep compile on demand.
```

The Studio owns interaction, visibility, and bounded actions. The core owns
durable knowledge, artifacts, sinks, and processing.

## Settled Decisions

### Source Catalog

Studio needs a new source catalog instead of stretching `processed_sources`.
The current `processed_sources` table means "this source has been processed and
published." It cannot faithfully represent metadata-only imports or independent
lifecycle dimensions.

The source catalog should represent library identity and lifecycle. Existing
`processed_sources` can remain as a compatibility/completion ledger while the
new model is introduced.

Public Studio source IDs should be stable opaque strings, such as generated
UUIDs or ULIDs. Integer primary keys may still be used internally. Deterministic
URL and content hashes remain matching and dedupe helpers, not public handles.

The source catalog may contain operational state that cannot be reconstructed
from the markdown vault. Losing the operational SQLite DB should degrade Studio
state, not destroy durable knowledge.

### Provider References

Source identity and provider sightings should be separate.

A single source may be known through Raindrop, Readwise, manual URL ingest, and
future providers. Provider-specific state belongs in provider reference rows,
not directly on the source identity row.

Provider metadata should use both normalized fields and flexible JSON. Fields
used for filtering, scoring, or UI should be queryable. Provider-specific
details should remain in JSON.

Tags should be normalized in a `source_tags` table with an origin such as
`provider`, `user`, `system`, or `theme`. A denormalized tag snapshot may be
kept on the source row for card rendering if useful.

### Import and Capture

First import should write source records for everything, but enqueue only the
prioritized subset. The queue should represent intended work, not a hidden
backlog of the entire library.

Metadata-only import is distinct from current `safe` mode. Current safe mode is
"no LLM enrichment but may fetch, archive, and publish fallback artifacts." The
new metadata-only stage should avoid fetching and avoid creating vault notes.

Metadata-only sources should appear in Studio Library, Search, and Source
Detail. They should not create markdown vault notes by default.

Capture crosses the durability boundary. A capture job should write raw
evidence and a minimal source note to the vault, plus JSON export when enabled.

Manual Add URL should create a source row first, then optionally enqueue
capture or brief generation in the same flow. Deep mode should not run
silently from URL add.

### Canonicalization and Dedupe

Metadata import should perform only lightweight URL normalization, such as
tracking-param stripping and known YouTube normalization. It should not fetch
remote pages or follow redirects across thousands of imported records.

Authoritative canonical URL resolution should happen during capture/fetch.

Duplicate handling should be conservative. Auto-merge only when identity is
very strong, such as exact canonical URL plus compatible source type or exact
content hash. Otherwise mark potential duplicates for user-visible review.

### Lifecycle Model

Lifecycle should use separate readiness/status dimensions, plus a derived
display state. A single authoritative enum is too lossy.

The model should track separate dimensions such as:

- metadata status
- content status
- brief status
- deep compilation status
- output status
- failure status and last failure reason

The Studio API can derive display states such as `metadata_only`,
`content_available`, `brief_ready`, `failed_partial`, or `deep_compiled`.

### Jobs, Queue, and Priority

Keep a durable work table, but tie work to `source_uid` or equivalent.

The queue should evolve toward source-linked jobs. A source can need many jobs:
capture, brief, deep compile, output generation, refresh, repair, or reprocess.

Priority should be deterministic and explainable at first. Persist both the
numeric priority score and the score breakdown, with a policy version and
computed timestamp. LLM-based priority can be added later as an optional
recommendation recipe.

Initial scoring should favor explicit user requests, videos, recent items,
pinned/favorited/provider-tagged items, and active topic scope. It should
penalize previous failures and already-enriched items.

Studio MVP should trigger bounded one-shot processing requests. It should not
own a persistent background worker. Existing OS scheduler and one-shot
automation remain compatible.

### Budget and Accounting

Budget usage should use explicit accounting records, not inference from
completed queue items.

Global caps are enough for the MVP UI, but the schema should allow future
overrides by task type, source type, and mode.

Budget records should be able to capture run, attempt, backend/model, task,
token estimates when available, estimated cost, and budget bucket.

Broad or expensive Studio actions need confirmation even when budget caps are
configured. Single-source capture, brief, and retry actions can be immediate
when within budget.

### Studio API

Studio library and status APIs should be SQLite/source-catalog-first. Read
model and JSON artifacts enrich the response, but they are not the primary
source for operational state.

Studio should have explicit API response schemas. The frontend should not bind
directly to JSON export file shape. JSON exports remain durable machine-facing
artifact serializations and are one input to Studio responses.

Source detail should use one composite endpoint for the initial page and lazy
subresources for heavy data:

- source metadata, lifecycle, provider refs, tags, artifact summary, related
  stubs, latest jobs, and actions in `GET /studio/sources/{source_id}`
- full artifact in an artifact subresource
- raw capture/transcript/evidence in a raw subresource
- expanded related-source browsing in a related subresource

Studio search must include metadata-only source catalog rows, not only read
model content. Search results should expose provenance such as metadata,
artifact, vault, or read-model match.

The MVP should include a narrow write surface:

- enqueue/enrich one source
- process a bounded queue run
- patch budget/settings
- save token-based provider setup

Bulk enrichment, destructive actions, output promotion, custom recipes, and
large reprocess operations should be deferred or confirmation-gated.

### Frontend and Packaging

The frontend should live inside the Epistora repository under `studio/`, while
remaining separately buildable.

Packaged installs should include built frontend assets so `epistora studio`
works without requiring users to install Node or run a frontend build.

Normal `epistora studio` should start FastAPI, serve built assets, and open the
browser unless `--no-open` is set. Dev mode should use or proxy to a Vite dev
server without initially owning that process.

The MVP should land on Library/Sources, not Reading Home. Source cards should
foreground lifecycle/readiness state. Placeholder-heavy pages should be avoided.

The first UI should include real backed pages for Library, Source Detail,
Queue/Status, Settings, and Search. Reading Home, Topic Bundles, Outputs,
Recipes, MCP status, and advanced customization can appear when their workflows
are real.

Use light/dark tokens for MVP. Defer broader themes, layout customization, and
user theme files.

Primary source views should render structured artifact/API fields through
trusted components. Markdown can remain a fallback, preview, raw view, or output
format.

Build generic source detail first, with schema room for rich YouTube blocks.
Rich YouTube views should follow once the generic lifecycle and artifact path
is stable.

### Settings and Security

Settings storage is split by data type:

- `.env` for secrets, backend settings, vault path, provider tokens, and server
  auth settings
- SQLite for queue state, runtime accounting, provider status cache, and
  operational state
- `.system/studio/*.yaml` for non-secret UI preferences, views, recipes, and
  later user customizations

Studio may update a bounded allowlist of known safe `.env` keys. It must not
act as an arbitrary `.env` editor.

Token-based provider setup should be supported in Studio for Raindrop and later
Readwise. Tokens are write-only from the frontend perspective and should be
validated by lightweight provider API calls.

`epistora studio` should bind to `127.0.0.1` by default and not require bearer
auth by default for localhost. If binding to non-localhost addresses, require
an API key or an explicit unsafe override.

### Durability, Backup, and Rebuild

The vault remains the durable human/agent knowledge product. Studio-only data
must not become the only copy of generated knowledge.

SQLite can hold operational state such as provider cursors, queue attempts,
priority scores, budgets, metadata-only imports, and UI state.

Metadata-only catalog entries should have a lightweight machine-readable
snapshot export, such as JSONL under `.system/exports/source_catalog/` or
`.system/studio/`. This protects manual URLs, deleted provider items, local
tags, and provider data that may not be re-syncable.

Snapshot export can be batch/event based, not transactionally updated after
every tiny state change. Provider imports, manual URL adds, bulk changes, and
manual "export catalog snapshot now" are sufficient for MVP.

If the operational DB is lost, Epistora should be able to rebuild read-model
state from the vault and partially reconstruct captured source catalog rows
from markdown/JSON artifacts. Metadata-only rows may require snapshot import or
provider re-sync.

### Readwise, Topic Bundles, and MCP

Readwise should be enabled by provider-neutral foundations first. The initial
Studio MVP can ship with Raindrop and manual URL flows, then add Readwise as
the next connector unless Readwise is required to validate the product promise.

Topic Bundles should come after the library/queue lifecycle loop is working.
The MVP should still support bundle-readiness queries: source set search,
readiness counts, source selection, and enqueue-top-N enrichment.

MCP should come after the Studio service layer. It should wrap the same search,
source detail, related-source, and output service functions instead of creating
a parallel model.

## Proposed Schema Outline

This is a shape guide, not final DDL.

`sources`

- Stable source identity and lifecycle.
- Key fields: internal id, public source UID, primary URL/title, normalized URL
  hash, canonical URL/hash when known, content hash when known, source type,
  saved/ingested/last-seen timestamps, lifecycle statuses, priority score,
  priority breakdown, failure fields, artifact/vault path pointers.

`source_provider_refs`

- Provider-specific sightings and sync metadata.
- Key fields: source id, provider, provider external id, original URL, saved
  date, provider location/collection/read state, favorite/pinned fields, raw
  provider metadata JSON.

`source_tags`

- Provider, user, system, and inferred theme tags.
- Key fields: source id, tag, origin, created timestamp, unique key on source,
  normalized tag, and origin.

`processing_jobs`

- Durable source-linked work requests.
- Key fields: source id, job type, mode, status, requested by, priority score,
  priority reasons, scheduled/started/finished timestamps, failure fields, and
  budget bucket.

`processing_attempts`

- Attempt history for jobs.
- Key fields: job id, attempt number, backend/model, status, started/finished
  timestamps, error type/message, changed paths.

`usage_events`

- Budget and cost accounting.
- Key fields: source id, job id, attempt id, backend, model, task, mode,
  estimated input/output tokens, estimated cost, actual cost when available,
  budget bucket, timestamp.

`source_catalog_snapshots`

- Optional bookkeeping for machine-readable catalog exports.
- Key fields: snapshot path, exported timestamp, row counts, source range or
  since timestamp, schema version.

## Immediate Implementation Order

1. Add this decisions document and link it from existing architecture/roadmap
   docs. _(done)_
2. Add source catalog schema, repository, and service. _(done)_
3. Teach provider discovery to write source rows, provider refs, and tags
   without fetching content by default. _(done)_
4. Add source-linked job enqueue and priority scoring. _(done)_
5. Add Studio API routes for status, sources, source detail, search, queue, and
   budget. _(done; budget remains future work)_
6. Add `epistora studio` server/static serving command. _(done)_
7. Build the frontend shell and real Library, Source Detail, Queue/Status,
   Settings, and Search pages. _(done; reader-first revamp landed with
   Library sections, Knowledge browse, combined Search, and editorial UI)_
8. Token-based provider setup UI and Studio Reader mini-tabs (deep view,
   YouTube enrichment, related sources). _(future slice)_
9. Budget views and bulk source actions with confirmation. _(future slice)_

## Deferred Decisions and Non-Goals

- Full Readwise importer details.
- MCP write tools and expensive tool confirmation UX.
- Rich YouTube summary page beyond generic source detail.
- Topic Bundle UI and output workflows.
- Full recipe builder.
- Theme presets beyond the editorial parchment palette (and a future dark mode).
- Persistent Studio-owned background daemon.
- Full vault-to-artifact round-trip editing (knowledge browse remains
  read-only; deep edits stay in the vault).
- Inline link expansion between knowledge notes (cross-links beyond simple
  navigation).
- Token-based provider setup UI inside Studio. Studio Settings can record a
  bearer token in browser storage but does not edit `.env` files. CLI
  `epistora connect raindrop` remains the supported path.
- Full desktop app packaging.
- Hosted sync, billing, collaboration, or cloud automation.

## Risks to Revisit

- Migration complexity between `queued_items`, `processed_sources`, and the new
  source/job tables.
- How much catalog state should be reconstructed from existing vaults during
  upgrade.
- Whether generated public source UIDs need alias tables after merges.
- How aggressively to estimate cost when backends do not expose token usage.
- Whether source catalog snapshots should become part of standard vault backup
  guidance.
