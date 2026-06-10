# Architecture

Epistora is a local-first knowledge compiler. It accepts saved sources from
connectors or direct URLs, preserves source evidence, compiles that evidence
into canonical artifacts, and publishes those artifacts into a markdown vault.

The vault is the durable product. SQLite databases support runtime state,
queues, Studio, chat, and derived retrieval, but they do not replace the vault as
the primary knowledge store.

## Runtime Boundary

```text
SourceItem
  -> SourceContent
  -> Source Brief / compiler analysis
  -> ArtifactBundle
  -> configured sinks
       -> markdown vault
       -> JSON export, when enabled
  -> derived read model refresh
```

There are two important ingest paths:

- Link-only sources, such as Raindrop or manual URLs, use fetchers to obtain
  content and can run the classic ingest graph end to end.
- Extracted-content sources, currently Readwise, can be imported into the source
  catalog without an LLM call, then compiled later through pending brief jobs.

Both paths converge on `ArtifactBundle` and the sink boundary.

## Topology

```text
CLI / FastAPI / Studio / automation
  -> services
     -> connectors and fetchers
     -> compiler and brief compilation
     -> backend router
     -> artifact bundle builder
     -> sinks
     -> vault/read-model/storage repositories
```

## Repository Map

| Area | Main files | Responsibility |
| --- | --- | --- |
| CLI | `app/cli/main.py` | Typer command tree and operator workflows |
| API | `app/main.py`, `app/api/` | FastAPI routes, Studio API, chat API |
| Services | `app/services/` | Application workflows for ingest, briefs, Studio, chat, review, query |
| Compiler | `app/compiler/` | LangGraph ingest/lint workflows and prompt composition |
| Artifacts | `app/artifacts/` | Canonical artifact models and bundle construction |
| Connectors | `app/connectors/` | Raindrop, Readwise, URL classification, fetcher dispatch |
| Backends | `app/backends/` | API/OpenCode/Claude Code/Codex backend abstraction |
| Sinks | `app/sinks/` | Markdown vault sink, JSON export sink, composite sink |
| Vault | `app/vault/` | Vault paths, rendering helpers, parser, indexes, logs |
| Read model | `app/read_model/` | Derived note catalog and lexical retrieval store |
| Retrieval | `app/retrieval/` | Query context selection over vault/read-model data |
| Automation | `app/automation/` | Queue discovery, processing, retry, scheduler helpers |
| Maintenance | `app/maintenance/` | Bounded structural/storage/semantic maintenance planning |
| Storage | `app/storage/` | Main SQLite schema, repositories, evidence blob policy |
| Plugins | `app/plugins/` | Local plugin manifest discovery and runtime loading |
| Studio UI | `studio/` | React/Vite frontend, built assets served from `studio/static/` |

## CLI Surface

Current command groups:

- Setup/status: `setup`, `doctor`, `help`, `status`, `init`
- Ingest: `ingest url`, `ingest latest`, `sync-raindrop`, `sync-readwise`,
  `sync-inbox`
- Source briefs: `brief pending`
- Query and outputs: `query`, `topic-bundle`, `review daily`,
  `review weekly`, `views rebuild`
- Vault health: `lint`, `rebuild-indexes`, `reset-generated`
- Vault management: `vault show`, `vault use`
- Backend and connectors: `backend status`, `backend setup`,
  `connect raindrop`, `connect readwise`
- Studio/API: `studio`
- Automation: `automation setup`, `automation discover`,
  `automation process-pending`, `automation maintain`,
  `automation run-pending`, `automation run-personal-learning`,
  `automation status`, `automation retry-failed`, `automation list-pending`,
  `automation generate-scheduler`

Hidden compatibility commands still exist for older workflows, but docs should
prefer the current command groups above.

## FastAPI And Studio

`app/main.py` mounts these route groups:

- Health: `/health`
- Ingest: `/ingest/*`
- Query: `/query`
- Review: `/review/*`
- Topic bundles: `/topic-bundle`
- Views: `/views/*`
- Lint: `/lint`
- Automation: `/automation/*`
- Studio: `/studio/*`
- Studio chat: `/studio/chat/*`

`GET /studio` serves the built React/Vite Studio from `studio/static/`.
`epistora studio` starts the API locally and opens that UI.

Studio exposes the source catalog, library filters, reader pages, metadata,
jobs, manual URL add, Readwise sync, pending brief compilation, knowledge browse,
combined search, snapshot import/export, chat settings, sidebar chat, and broad
chat. The frontend reads rendered vault files through API responses; it does not
make JSON export the UI contract.

Protected API routes use bearer auth only when `EPISTORA_API_KEY` is set.
`/health` remains unauthenticated.

## Source Catalog And Processing State

The main SQLite database tracks both old completed-source state and the newer
source catalog:

- `processed_sources`: compatibility/completed-source ledger.
- `sources`: catalog identity and lifecycle state.
- `source_provider_refs`: provider sightings such as Readwise or Raindrop IDs.
- `source_tags`: normalized provider/user/system tags.
- `processing_jobs` and `processing_attempts`: source-linked queue work.
- `usage_events`: backend/model usage records.
- `source_catalog_snapshots`: exported catalog snapshots.
- `chat_conversations`, `chat_messages`, `chat_settings`: Studio chat state.

Catalog snapshots are JSONL exports under `.system/exports/source_catalog/`.
They are useful recovery artifacts for metadata-only and queue state, but the
vault remains the durable knowledge layer.

## Artifact Layer And Sinks

`app/artifacts/models.py` defines the canonical compiler boundary:

- `SourceArtifact`
- `TopicArtifact`
- `EntityArtifact`
- `ConceptArtifact`
- `RelationshipArtifact`
- `SynthesisArtifact`
- `EvidenceReference`
- `ArtifactBundle`

Sinks consume `ArtifactBundle` objects:

- `markdown_vault` is the default sink.
- `json_export` writes deterministic machine-readable bundle JSON.
- Multiple sinks can be enabled with `ARTIFACT_SINK_IDS`, for example
  `markdown_vault,json_export`.

The markdown sink renders raw captures, source notes, topic/entity/concept hubs,
synthesis notes, index pages, and read-model refreshes. Oversized raw evidence
is represented by a visible manifest in `raw/` and a full blob under
`.system/blobs/`.

## Vault Layout

```text
vault/
  AGENTS.md
  raw/
  wiki/
    sources/
    topics/
    entities/
    concepts/
    synthesis/
    indexes/
    logs/
  outputs/
    digests/
  .system/
    blobs/
    exports/
    state/
    prompts/
```

`wiki/sources/` is the primary durable retrieval unit. `raw/` is the stable
evidence entrypoint. `outputs/` contains generated reports and digests that are
not automatically promoted to durable knowledge. `.system/` contains derived
state, exports, local prompt overrides, and heavy evidence blobs.

## Prompt Layering

Prompt composition lives in `app/compiler/prompts.py`.

Prompt roots are searched in this order:

1. `EPISTORA_PROMPTS_DIR`
2. active prompt-pack plugin selected by `EPISTORA_PROMPT_PACK`
3. built-in `prompts/`

Optional task/profile/backend layers can be supplied from prompt roots or from
the vault under `.system/prompts/`. The built-in prompt tree includes the
`personal_learning` profile.

Current task names include `ingest_analysis`, `query_answer`, `lint_analysis`,
and `topic_bundle`.

## Backend Routing

The backend router supports:

- `api`: OpenAI-compatible direct API through LangChain.
- `opencode`: OpenCode CLI.
- `claude_code`: Claude Code CLI.
- `codex`: Codex CLI.

Fallback order is configured per task:

- `BACKEND_ORDER_INGEST`
- `BACKEND_ORDER_QUERY`
- `BACKEND_ORDER_LINT`

Automation modes have their own backend order overrides:

- `AUTOMATION_BACKEND_ORDER_SAFE`
- `AUTOMATION_BACKEND_ORDER_BALANCED`
- `AUTOMATION_BACKEND_ORDER_DEEP`

## Automation And Maintenance

Queue automation has three modes:

- `safe`: low-cost capture/archive behavior.
- `balanced`: bounded enrichment and focused maintenance.
- `deep`: richer enrichment and broader bounded maintenance.

`automation run-pending` performs discovery, processing, and optional
maintenance once. `automation run-personal-learning` adds the personal-learning
profile, read-model refresh, reader view rebuilds, review digest evaluation, and
bounded maintenance.

Maintenance plans structural repair, hub refresh, backlink repair, candidate
synthesis refresh, read-model refresh, and search refresh. It is scoped by the
changed notes from processing when possible.

## Plugins

Plugins are discovered from:

- `plugins/` inside the checkout, when present
- `$EPISTORA_HOME/plugins`
- paths in `EPISTORA_PLUGIN_DIRS`

Manifests can contribute prompt packs, inbox providers, reasoning backends, and
sinks. `epistora doctor` reports plugin discovery and sink health.

## Security Boundary

Epistora is intended for local-first or trusted deployments. User-supplied fetch
URLs are constrained to public `http`/`https` targets with SSRF guardrails and
redirect validation. If the API is reachable beyond localhost, set
`EPISTORA_API_KEY`.
