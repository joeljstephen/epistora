# Epistora v2 Architecture Specification

## Status

Draft v1

## Purpose

This document is the main architecture specification for **Epistora v2**. It defines the long-term target architecture for turning Epistora from a good local-first knowledge compiler into a more extensible, scalable, and reusable knowledge platform.

This spec is intended to guide:

- system design
- implementation planning
- open-source packaging
- plugin boundaries
- contributor decisions
- roadmap sequencing
- future integrations and downstream products

It is designed to improve on the weaknesses of the current architecture while preserving the strongest parts of Epistora's existing philosophy.

---

# 1. Executive Summary

Epistora v2 is a **local-first knowledge compiler platform**.

It ingests content from inboxes and direct sources, preserves raw evidence, compiles that evidence into canonical knowledge artifacts, and publishes those artifacts into one or more output sinks such as a markdown vault, Notion, JSON exports, or future read models.

The core architectural shift in v2 is this:

**Epistora should stop thinking of itself primarily as a markdown writer and instead think of itself as a compiler of reusable knowledge artifacts.**

The markdown vault remains the primary user-facing output and the most important default sink, but it is no longer the only form the system can think in.

Epistora v2 should be:

- local-first
- source-aware
- evidence-preserving
- agent-friendly
- highly extensible
- retrieval-aware
- maintenance-capable
- usable as a standalone CLI and as a reusable dependency for other systems

---

# 2. Core Product Direction

## 2.1 What Epistora is

Epistora is a knowledge compiler that sits between raw saved material and durable usable knowledge.

It should:

- discover or accept source material
- fetch the real source content
- preserve evidence in an immutable form
- generate structured source-level understanding
- extract topics, entities, concepts, claims, and relationships
- maintain higher-level knowledge artifacts over time
- support agents querying and operating on the resulting knowledge system
- allow other tools to build on top of the compiled knowledge layer

## 2.2 What Epistora is not

Epistora is not primarily:

- a generic chat-with-files product
- a hosted SaaS-first note app
- a giant life operating system
- a universal assistant platform
- a single-purpose RAG API wrapper

## 2.3 Product Positioning

Near-term positioning:

- local-first knowledge compiler
- developer/researcher/creator knowledge vault pipeline
- reusable infrastructure for LLM-maintained knowledge bases

Long-term positioning:

- open-source knowledge substrate for personal and team knowledge systems
- a foundational layer for products built around knowledge compilation, synthesis, and agent navigation

---

# 3. Design Goals

## 3.1 Primary Goals

1. Preserve user ownership through a local-first durable knowledge layer.
2. Separate evidence from compiled understanding from temporary outputs.
3. Support filesystem-capable agents as first-class users.
4. Make extension possible without forking core.
5. Scale from small personal vaults to larger and more complex corpora.
6. Keep the system useful even without hosted infrastructure.
7. Allow future use as a dependency in other products and interfaces.

## 3.2 Secondary Goals

1. Provide a polished open-source CLI experience.
2. Support multiple inbox providers and reasoning backends.
3. Support multiple output sinks.
4. Keep maintenance and enrichment cost-aware.
5. Make future UI layers easy to add.

## 3.3 Non-Goals

Epistora v2 should not initially try to:

- become a universal hosted collaboration product
- own every messaging channel or chat UI itself
- replace downstream tools like OpenClaw
- require a vector database for all users
- require a graph database for all users
- turn all domain-specific use cases into core product features

---

# 4. Architectural Principles

## 4.1 Local-First Durable Outputs

The durable product is the user-owned knowledge layer, not a transient model response.

## 4.2 Raw Evidence Is Immutable

Raw captures are source-of-truth evidence and should not be silently mutated.

## 4.3 Compiled Knowledge Is Maintainable

Source notes, hub pages, synthesis notes, and higher-level artifacts are intended to evolve and improve over time.

## 4.4 Scratch Outputs Stay Separate

Temporary answers and reports are not automatically treated as durable knowledge.

## 4.5 Files Remain the Canonical Human-Facing Artifact

The vault remains the primary inspectable artifact, but it is not the only internal representation.

## 4.6 Canonical Knowledge Objects Exist Before Rendering

The compiler should produce structured artifacts first, then publish them into one or more sinks.

## 4.7 Agent-First Querying Remains the Default

The system should still be easy for a filesystem-capable agent to navigate directly.

## 4.8 Retrieval Is Layered

Use structure first, search second, and raw evidence drilldown last.

## 4.9 Maintenance Is a First-Class System

The vault should improve over time through structural, semantic, synthesis, and storage maintenance.

## 4.10 Extension Should Be a Product Feature

Connectors, backends, prompt packs, sinks, and advanced retrieval modules should be addable without editing core code.

---

# 5. High-Level v2 Architecture

## 5.1 Main Layers

Epistora v2 has six major architectural layers:

1. Discovery Layer
2. Evidence Layer
3. Compiler Layer
4. Knowledge Model Layer
5. Sink / Output Layer
6. Maintenance and Retrieval Layer

These sit on top of shared storage and plugin infrastructure.

## 5.2 High-Level Flow

```text
Inputs / Inboxes / URLs
        |
        v
   Discovery Layer
        |
        v
   Evidence Layer
        |
        v
   Compiler Layer
        |
        v
 Canonical Knowledge Artifacts
        |
        +-------------------+
        |                   |
        v                   v
 Sink / Output Layer   Retrieval / Read Model Layer
        |                   |
        v                   v
 Markdown Vault       Search / Graph / Query Aids
        |
        v
 Agents / Tools / Downstream Products
```

---

# 6. Discovery Layer

## 6.1 Responsibility

The Discovery Layer is responsible for finding and staging items to ingest.

## 6.2 Inputs

Possible discovery sources include:

- Raindrop
- Readwise Reader
- manual URLs
- RSS saved items
- browser extension inboxes
- filesystem watch folders
- CSV / JSON imports
- future app-specific inbox providers

## 6.3 Output

Every discovery provider must emit a normalized **DiscoveredItem**.

## 6.4 DiscoveredItem Schema

Suggested fields:

- `provider_id`
- `external_id`
- `source_url`
- `canonical_candidate_url`
- `title`
- `saved_at`
- `discovered_at`
- `tags`
- `provider_metadata`
- `source_hint`
- `ingest_priority`
- `trust_class_hint` (optional)

## 6.5 Discovery Responsibilities

- connector auth and pagination
- cursor management
- duplicate staging avoidance
- durable queue insertion
- provider metadata preservation

## 6.6 Design Rules

- Discovery must be idempotent.
- Sync cursors must advance only after durable staging.
- Providers should not be assumed to be the source-of-truth for full content.
- Discovery plugins must not leak provider-specific assumptions into later layers.

---

# 7. Evidence Layer

## 7.1 Responsibility

The Evidence Layer fetches and normalizes real source content into a standard evidence package.

## 7.2 Core Output: Source Bundle

The main output of the Evidence Layer is a **SourceBundle**.

## 7.3 SourceBundle Schema

Suggested fields:

- `source_id`
- `source_type`
- `canonical_url`
- `original_url`
- `title`
- `author`
- `published_at`
- `provider_context`
- `content_hash`
- `media_hash` (optional)
- `best_text`
- `best_text_excerpt`
- `raw_capture_refs`
- `archived_markdown_ref`
- `transcript_ref`
- `metadata`
- `extraction_quality`
- `extraction_method`
- `extraction_attempts`
- `evidence_confidence`
- `provenance`
- `rights_or_license_notes` (optional)

## 7.4 Source Types

Default source types:

- article
- youtube
- x_thread
- pdf
- generic
- future extensions via plugin

## 7.5 Extraction Strategy

The evidence layer may run multiple extractors and choose the strongest available result.

Examples:

- article extraction pipeline
- readability fallback
- browser-rendered extraction
- transcript extraction
- subtitle fallback
- API-based thread extraction
- mirror-based fallback
- PDF extraction
- metadata-only fallback

## 7.6 Evidence Quality Levels

- `full`
- `mostly_full`
- `partial`
- `metadata_only`
- `failed`

## 7.7 Evidence Retention Policy

Raw evidence should usually be retained, but not all evidence must remain in the hot working set.

Recommended tiers:

- hot: slim readable captures used frequently
- warm: archived raw text / markdown
- cold: large blobs stored in `.system/blobs/` or external blob root

## 7.8 Evidence Layer Rules

- downstream compiler logic should operate on SourceBundle, not extractor-specific outputs
- evidence provenance must remain inspectable
- raw evidence must remain auditable
- large evidence should be preservable without bloating the visible vault

---

# 8. Compiler Layer

## 8.1 Responsibility

The Compiler Layer transforms evidence into structured knowledge artifacts.

## 8.2 Compiler Stages

1. Normalize Evidence
2. Analyze Source
3. Extract Structured Knowledge
4. Resolve / Merge Against Existing Knowledge
5. Generate Canonical Artifacts
6. Publish to Sinks

## 8.3 Stage 1: Normalize Evidence

Determine the best usable evidence and build compiler-ready input.

## 8.4 Stage 2: Analyze Source

Produce structured source-level understanding.

Expected outputs may include:

- summary
- 5-minute read
- detailed reading note
- key ideas
- examples
- takeaways
- why it matters
- open questions
- confidence notes
- contradictions or uncertainty notes
- audience fit

## 8.5 Stage 3: Extract Structured Knowledge

Extract:

- topics
- entities
- concepts
- claims
- evidence anchors
- related source signals
- relationships
- trust signals

## 8.6 Stage 4: Resolve / Merge

Resolve new artifacts against existing knowledge.

Tasks include:

- normalize naming
- merge near-duplicate topics
- map entities to existing hubs
- preserve stable slugs and canonical titles
- avoid hub explosion

## 8.7 Stage 5: Generate Canonical Artifacts

This stage creates internal structured objects, not final files yet.

Core artifact types:

- SourceArtifact
- TopicArtifact
- EntityArtifact
- ConceptArtifact
- RelationshipArtifact
- SynthesisArtifact
- EvidenceReference
- ClaimArtifact (optional but recommended)

## 8.8 Stage 6: Publish to Sinks

After canonical artifacts are ready, they are rendered into one or more sinks.

---

# 9. Canonical Knowledge Model

## 9.1 Purpose

The canonical model is the main architectural upgrade in v2.
It lets Epistora think in terms of structured knowledge before rendering to markdown or other targets.

## 9.2 Core Artifact Types

### SourceArtifact

Represents one compiled source and its structured understanding.

Suggested fields:

- `id`
- `slug`
- `title`
- `source_type`
- `summary`
- `detailed_note`
- `key_ideas`
- `quotes`
- `examples`
- `takeaways`
- `topics`
- `entities`
- `concepts`
- `claims`
- `raw_refs`
- `quality`
- `trust_class`

### TopicArtifact

Represents an evolving subject across multiple sources.

Suggested fields:

- `id`
- `slug`
- `title`
- `summary`
- `source_refs`
- `related_topics`
- `related_entities`
- `related_concepts`
- `patterns`
- `conflicts`
- `gaps`

### EntityArtifact

Represents named things.

Suggested fields:

- `id`
- `slug`
- `title`
- `entity_type`
- `summary`
- `contexts`
- `source_refs`
- `related_concepts`
- `related_topics`

### ConceptArtifact

Represents abstractions.

Suggested fields:

- `id`
- `slug`
- `title`
- `definition`
- `examples`
- `related_concepts`
- `source_refs`
- `gaps`

### RelationshipArtifact

Represents explicit edges between artifacts.

Examples:

- source mentions entity
- source supports claim
- topic related to concept
- concept conflicts with concept
- synthesis supported by source

### EvidenceReference

Represents traceable support.

Suggested fields:

- `source_id`
- `raw_ref`
- `excerpt`
- `offset_or_section`
- `confidence`

### SynthesisArtifact

Represents higher-level durable notes built from multiple sources.

Suggested fields:

- `id`
- `slug`
- `title`
- `summary`
- `source_basis`
- `patterns`
- `disagreements`
- `reusable_takeaways`

### ClaimArtifact (Recommended)

Especially useful for expert disagreement or trust-weighted use cases.

Suggested fields:

- `id`
- `claim_text`
- `supporting_sources`
- `opposing_sources`
- `trust_weight`
- `claim_status`

---

# 10. Sink / Output Layer

## 10.1 Responsibility

The Sink Layer publishes canonical artifacts into user-facing or machine-facing targets.

## 10.2 Core Principle

The vault is the primary default sink, but not the only possible sink.

## 10.3 Default Sink Types

- MarkdownVaultSink
- JsonExportSink
- NotionSink
- StaticSiteSink (future)
- ReadModelSink (optional)

## 10.4 Markdown Vault Sink

This is the primary sink and must remain excellent.

It should render:

- raw references
- source notes
- topics
- entities
- concepts
- synthesis notes
- indexes
- logs
- AGENTS.md and query instructions

## 10.5 Vault Structure

Recommended visible vault layout:

```text
knowledge-vault/
  AGENTS.md
  raw/
    articles/
    videos/
    threads/
    pdfs/
    misc/
  wiki/
    sources/
    topics/
    entities/
    concepts/
    synthesis/
    indexes/
    logs/
  outputs/
    answers/
    digests/
    reports/
  .system/
    db/
    cache/
    state/
    manifests/
    plugins/
    blobs/
    jobs/
    archives/
```

## 10.6 Output Rules

- human-friendly vault files remain readable
- sink rendering must be deterministic where possible
- temporary answers must not be silently promoted into durable synthesis
- sinks should be independently configurable

---

# 11. Retrieval and Read Model Layer

## 11.1 Responsibility

The Retrieval Layer provides fast, structured, scalable query assistance without replacing the files as the source of truth.

## 11.2 Core Idea

Use a layered retrieval model:

1. structured navigation
2. relationship expansion
3. lexical or hybrid search
4. raw evidence drilldown

## 11.3 Read Model

The read model is a derived local helper representation of the vault.

It should store:

- note catalog
- note type metadata
- backlinks
- artifact relationships
- source-to-topic/entity/concept mappings
- maintenance hints
- index freshness state

## 11.4 Default Read Model Storage

SQLite inside `.system/db/`.

## 11.5 Relationship Graph

Epistora should maintain an internal relationship graph as a derived read model.

This does **not** require a dedicated graph database.

Nodes may include:

- source notes
- topic pages
- entity pages
- concept pages
- synthesis notes

Edges may include:

- belongs_to_topic
- mentions_entity
- related_concept
- supports_synthesis
- derived_from_source
- backlinks_to

## 11.6 Search

Default search should use:

- SQLite FTS or equivalent lexical search
- frontmatter-aware filtering
- path/type filtering
- optional reranking

## 11.7 Optional Search Plugins

- pgvector retrieval plugin
- Qdrant retrieval plugin
- qmd/local hybrid retrieval plugin
- future cloud retrieval plugins

## 11.8 Retrieval Rules

- the canonical human-facing truth remains in files
- the read model may be rebuilt from the vault
- optional advanced retrieval should not be mandatory for all users

---

# 12. Query Architecture

## 12.1 Preferred Query Path

Agent-first querying remains the default.

Recommended flow:

1. read `AGENTS.md`
2. read `START_HERE.md`
3. read `QUERY_PROTOCOL.md`
4. inspect indexes
5. open relevant hub pages
6. expand to related artifacts via read model
7. read key source notes
8. consult raw evidence only if necessary
9. answer with structure and evidence awareness

## 12.2 Query Support Modes

### Mode A: Direct Filesystem Agent

Examples:

- OpenCode
- Claude Code
- Codex

These agents operate directly on the vault and may optionally call Epistora helper commands.

### Mode B: Tool-Driven Query

An external system calls Epistora CLI/API/MCP tools and receives structured context back.

### Mode C: Hybrid

A hosting platform such as OpenClaw orchestrates a filesystem-capable agent and optionally uses Epistora retrieval helpers.

## 12.3 Built-In Query Path

The old built-in query path should not be central in v2.

Options:

- keep only as a debugging fallback
- replace with a cleaner read-model query service
- or remove once equivalent helper tooling exists

---

# 13. Maintenance Architecture

## 13.1 Responsibility

Maintenance ensures the vault improves as it grows.

## 13.2 Maintenance Classes

### Structural Maintenance

Checks:

- broken raw refs
- missing backlinks
- thin pages
- orphan pages
- invalid frontmatter
- stale indexes

### Semantic Maintenance

Improves:

- summaries
- backlinks
- near-duplicate merges
- topic rollups
- hub quality
- wording compactness
- clarity and structure

### Synthesis Maintenance

Promotes:

- repeated patterns
- cross-source summaries
- conflict maps
- disagreement notes
- knowledge gaps

### Storage / Retrieval Maintenance

Maintains:

- hot/warm/cold storage movement
- blob compaction
- index freshness
- read-model repair
- FTS refresh
- stale artifact cleanup

## 13.3 Maintenance Triggers

- scheduled runs
- after N new sources
- after significant topic growth
- manual user trigger
- explicit deep maintenance mode

## 13.4 Maintenance Output

Maintenance should update:

- hub pages
- synthesis notes
- indexes
- logs
- maintenance metadata

It should never silently delete important evidence.

---

# 14. Automation Architecture

## 14.1 Core Automation Flow

The queue-based model remains the foundation.

Recommended flow:

- discover
- stage
- process
- maintain

## 14.2 Queue Model

Each queued item should track:

- provider
- external ID
- source URL
- status
- saved_at
- discovered_at
- attempt_count
- next_attempt_at
- failure_class
- last_error
- processing_mode
- last_backend_used
- produced_artifact_ids

## 14.3 Processing Modes

### Safe

- evidence fetch
- raw preservation
- minimal source artifact
- no LLM cost
- minimal index update

### Balanced

- source analysis
- limited hub updates
- budget-aware enrichment
- targeted maintenance on changed neighborhoods

### Deep

- full source analysis
- full hub propagation
- synthesis candidate generation
- semantic maintenance
- optional trust-aware claim processing

## 14.4 Important Improvement Over v1

Balanced and Deep must differ in actual processing behavior, not merely budget policy.

## 14.5 Schedulers

Epistora should provide scheduler helpers for:

- macOS launchd
- Linux systemd
- Windows Task Scheduler

The core logic remains one-shot command based.

---

# 15. Storage Architecture

## 15.1 Philosophy

Storage should remain simple, portable, and user-controlled.

## 15.2 Main Storage Types

### Visible Vault Files

- markdown notes
- indexes
- logs
- lightweight raw captures

### Local System State

Inside `.system/db/`:

- metadata DB
- read-model DB
- search DB
- queue state

### Blob Storage

Inside `.system/blobs/` or optional external blob root:

- large transcripts
- extracted PDF text
- raw HTML snapshots
- large evidence bundles

## 15.3 Sync Guidance

- vault files are primary sync artifacts
- helper databases are rebuildable local caches/read models where possible
- avoid assuming many machines write the same SQLite files simultaneously

## 15.4 Git Guidance

Recommended git behavior:

- commit curated markdown when useful
- exclude caches, generated search DBs, and heavy raw blobs by default
- optionally version lightweight raw captures
- do not assume the entire hot system state should live in git

## 15.5 Vault Size Expectations

- curated markdown is usually small
- raw evidence dominates storage
- SQLite metadata is usually modest relative to source evidence

---

# 16. Plugin Architecture

## 16.1 Goal

Extension should be possible without editing core code.

## 16.2 Plugin Types

- `inbox_provider`
- `extractor`
- `reasoning_backend`
- `prompt_pack`
- `sink`
- `maintenance_plugin`
- `retrieval_provider` (optional)
- `artifact_enricher` (optional)

## 16.3 Plugin Manifest

Each plugin should declare:

- plugin ID
- version
- compatibility range
- plugin type
- config schema
- capabilities
- entrypoints
- install requirements

## 16.4 Plugin Rules

- plugins must not directly corrupt canonical artifacts
- plugins must declare version compatibility
- plugin outputs must be normalized into Epistora core models
- plugin failures must be isolated and visible

## 16.5 Core vs Plugin Boundary

Core should own:

- canonical artifact model
- base queue automation
- base storage model
- base read model
- default vault sink
- maintenance framework

Plugins should extend:

- discovery providers
- extractors
- reasoning providers
- optional sinks
- optional retrieval engines
- prompt styles
- specialized artifact enrichers

---

# 17. Prompt System Architecture

## 17.1 Goal

Prompt behavior should be customizable without rewriting core logic.

## 17.2 Prompt Layers

Suggested composition order:

1. base compiler instructions
2. artifact-type instructions
3. source-type instructions
4. workspace profile instructions
5. user overrides
6. backend/model-specific hints

## 17.3 Prompt Pack Examples

- research-heavy wiki
- concise study mode
- creator knowledge base
- executive summary mode
- disagreement surfacing mode
- citation-heavy mode

## 17.4 Prompt System Rules

- prompts should be discoverable and overrideable
- prompt packs should be installable as plugins
- prompt composition should be inspectable for debugging

---

# 18. Trust, Claims, and Disagreement Handling

## 18.1 Why This Matters

Some advanced use cases require more than summarization.
They need trust-aware, claim-aware knowledge handling.

## 18.2 Trust Classes

Optional trust classes may include:

- self-authored
- mentor
- vetted
- unvetted
- unknown

## 18.3 Claim Layer

For advanced profiles, Epistora may extract claims explicitly.
This supports:

- disagreement surfacing
- reference article generation
- curriculum synthesis
- source comparison

## 18.4 Human Judgment Boundary

Epistora may assist in surfacing conflicts and evidence, but some use cases may intentionally keep final judgment with the user.

---

# 19. Downstream Integrations and Reuse

## 19.1 Epistora as a Dependency

Epistora should be usable as a standalone engine by:

- OpenClaw
- web UIs
- course compilers
- creator research systems
- policy intelligence tools
- custom internal knowledge tools

## 19.2 Integration Modes

- CLI invocation
- HTTP API
- local SDK / Python package
- MCP server
- artifact export pipeline

## 19.3 Scope Rule

Epistora core should provide the reusable knowledge substrate.
It should not try to own every downstream surface.

---

# 20. Open-Source Packaging and Distribution

## 20.1 Primary Form

Epistora should ship as a Python CLI first.

## 20.2 Install Story

Preferred workflow:

- `uv tool install epistora`
- `epistora setup`
- `epistora doctor`

## 20.3 Setup Wizard

The setup wizard should configure:

- vault location
- first inbox provider
- backend provider(s)
- prompt profile
- processing mode
- scheduler helpers
- optional storage policy

## 20.4 Repo Hygiene

The repo should include:

- README
- docs site or docs folder
- LICENSE
- CONTRIBUTING
- SECURITY
- CODE_OF_CONDUCT
- issue templates
- plugin author guide
- `.env.example`
- sample vault template

---

# 21. Security and Privacy

## 21.1 Local-First Default

The default mode should not require sending the entire knowledge base to a hosted service.

## 21.2 Principle of Least Exposure

Only the minimal required evidence should be sent to reasoning backends.

## 21.3 User Control

Users should be able to choose:

- local-only workflows
- API backends
- external blob roots
- backup/sync strategy

## 21.4 Sensitive Sources

The system should provide config hooks for:

- source exclusion
- tag-based exclusion
- restricted sync or export

---

# 22. Observability and Debugging

## 22.1 Required Diagnostics

- ingest logs
- maintenance logs
- queue run history
- artifact generation summaries
- prompt composition debugging
- extraction fallback chain visibility
- backend failure reporting

## 22.2 Doctor Command

`epistora doctor` should check:

- vault integrity
- DB availability
- plugin health
- connector auth
- backend availability
- scheduler health
- write permissions

---

# 23. Migration from Current Architecture

## 23.1 Migration Strategy

Do not rewrite everything at once.

## 23.2 Recommended Order

### Phase 1

Introduce canonical internal artifacts while keeping current vault output.

### Phase 2

Refactor current vault writer into MarkdownVaultSink.

### Phase 3

Add plugin manifest system and public plugin APIs.

### Phase 4

Add second sink, preferably JSON or Notion, to prove sink independence.

### Phase 5

Add richer read model with relationship edges and incremental indexing.

### Phase 6

Refine maintenance pipeline and real Deep mode.

## 23.3 Backward Compatibility

- current vaults should remain readable
- migration tooling should update `.system/` layout if needed
- old deprecated query path may be kept temporarily as fallback

---

# 24. Implementation Priorities

## 24.1 High Priority

- canonical artifact model
- MarkdownVaultSink refactor
- read model foundation
- plugin system foundation
- improved maintenance design
- storage tier support

## 24.2 Medium Priority

- second sink
- trust/claim layer
- retrieval plugins
- advanced prompt packs

## 24.3 Lower Priority

- hosted sync
- dedicated UI
- advanced collaborative workflows

---

# 25. Acceptance Criteria for v2

Epistora v2 should be considered architecturally successful if:

1. New inbox providers can be added without changing core code.
2. New reasoning backends can be added without changing core compiler logic.
3. Prompt behavior can be overridden without forking core.
4. The compiler produces canonical artifacts before sink rendering.
5. The vault remains excellent as the default sink.
6. The system can keep large raw evidence without bloating the main working layer.
7. The read model can answer relationship queries without rereading the whole vault.
8. Maintenance can improve the vault over time, not just lint it.
9. Downstream tools can use Epistora through CLI/API/SDK/MCP.
10. The system remains usable locally without mandatory hosted infrastructure.

---

# 26. Example End-to-End v2 Query Flow

## Example: Agent asks about a topic

User asks through OpenCode or OpenClaw:

> What does my knowledge base say about agent memory, and what should I read next?

### Flow

1. Agent reads `AGENTS.md` and query protocol.
2. Agent resolves the main topic artifact.
3. Read model expands nearby concepts, entities, synthesis notes, and source notes.
4. Agent reads the topic hub and top source notes.
5. If needed, agent drills into raw evidence for exact wording.
6. Agent answers with:
   - direct findings
   - related ideas
   - disagreements or gaps
   - recommended next notes

This flow uses:

- files as truth
- read model as fast map
- search as candidate helper
- raw evidence as final drilldown layer

---

# 27. Final One-Paragraph Definition

Epistora v2 is a local-first knowledge compiler platform that discovers sources, preserves raw evidence, compiles that evidence into canonical knowledge artifacts, maintains a structured and improving knowledge layer over time, and publishes those artifacts into one or more sinks such as a markdown vault or future integrations. It keeps files as the primary human-facing artifact, adds a derived read model for fast relationships and retrieval, supports plugins for providers/backends/prompts/sinks, and is designed to be useful both as a standalone CLI and as a knowledge substrate for other systems.

---

# 28. Recommended Next Step

The next implementation document should be a **v2 technical design breakdown** covering:

- package/module boundaries
- concrete artifact schemas
- plugin manifest format
- read-model schema
- sink interfaces
- migration plan from the current codebase
- phased implementation tickets
