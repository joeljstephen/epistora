# Epistora

Epistora is a local-first knowledge compiler. It imports saved sources, captures
their evidence, compiles source briefs and knowledge artifacts, and publishes the
result into a markdown vault that works well in Obsidian and with
filesystem-capable agents.

The markdown vault is the durable product. SQLite supports runtime state,
catalog search, queues, chat history, and derived read models, but it is not the
primary knowledge store.

## What It Supports

- Inputs: Readwise Reader, Raindrop, and direct URL ingest.
- Source types: articles, YouTube videos, X/Twitter threads, PDFs, and generic
  web pages.
- Outputs: markdown vault by default, optional deterministic JSON artifact
  export.
- Interfaces: Typer CLI, FastAPI API, and a local React/Vite Studio served at
  `/studio`.
- Reasoning backends: OpenAI-compatible API, OpenCode CLI, Claude Code CLI, and
  Codex CLI with per-task fallback order.
- Automation: queue-based discovery, processing, retry, maintenance, and a
  personal-learning workflow preset.

## Quick Start

```bash
uv sync --extra dev
uv run epistora setup
uv run epistora doctor
uv run epistora ingest url "https://example.com/article"
```

Installed CLI:

```bash
uv tool install .
epistora setup
epistora doctor
epistora ingest latest --limit 1
```

Short alias:

```bash
eps help
```

## Everyday Commands

| Command | What it does |
| --- | --- |
| `epistora setup` | Guided first-time setup |
| `epistora doctor` | Checks config, vault, backends, sinks, plugins, and storage |
| `epistora ingest url <url>` | Fetch, compile, and publish one URL |
| `epistora ingest latest --limit 1` | Ingest recent Raindrop items |
| `epistora sync-readwise --limit 25` | Import Readwise items into the source catalog |
| `epistora brief pending --limit 5` | Compile pending catalog sources into vault notes |
| `epistora studio` | Start the local API and open Studio |
| `epistora status` | Show active vault and runtime stats |
| `epistora vault show` | Show the active vault path |
| `epistora vault use <path>` | Switch to another vault |

Advanced commands:

| Command | What it does |
| --- | --- |
| `epistora connect raindrop` | Configure Raindrop credentials |
| `epistora connect readwise` | Configure Readwise credentials |
| `epistora backend status` | Show backend availability |
| `epistora backend setup` | Configure backend defaults interactively |
| `epistora sync-raindrop --limit 10` | Sync Raindrop through the classic ingest flow |
| `epistora sync-inbox --connector raindrop` | Sync a configured link-only inbox connector |
| `epistora lint` | Run vault health checks |
| `epistora rebuild-indexes` | Rebuild vault index pages |
| `epistora views rebuild` | Rebuild reader-style index views |
| `epistora topic-bundle <topic>` | Generate a grounded topic packet |
| `epistora review daily` | Generate a daily review digest when enough signal exists |
| `epistora review weekly` | Generate a weekly review digest when enough signal exists |
| `epistora reset-generated` | Clear generated artifacts while keeping the vault shell |
| `epistora automation run-pending` | Discover, process, and optionally maintain once |
| `epistora automation run-personal-learning` | Run the composed personal-learning preset |

## How It Works

```text
Readwise / Raindrop / URL
  -> connector or fetcher
  -> SourceContent
  -> Source Brief / compiler analysis
  -> ArtifactBundle
  -> configured sinks
       -> markdown vault
       -> optional JSON export
  -> derived read model and Studio catalog state
```

Typical vault layout:

```text
your-vault/
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
```

Large raw evidence is kept auditable without bloating visible notes. Compiled
source notes live in `wiki/sources/`, raw manifests live in `raw/`, and
oversized full payloads can be stored under `.system/blobs/`.

## Configuration

Run `epistora setup` for the normal path. Manual configuration is environment
variable based.

When run from a source checkout, Epistora prefers the checkout `.env`. When run
as an installed tool, it uses the OS-specific Epistora config directory unless
`EPISTORA_ENV_FILE` is set.

Important settings:

| Variable | Description |
| --- | --- |
| `VAULT_PATH` | Active markdown vault |
| `DATABASE_URL` | Main SQLite database |
| `EPISTORA_API_KEY` | Optional bearer token for protected API routes |
| `RAINDROP_API_TOKEN` | Raindrop connector token |
| `READWISE_API_TOKEN` | Readwise Reader connector token |
| `ARTIFACT_SINK_IDS` | Comma-separated sinks. Default: `markdown_vault` |
| `JSON_EXPORT_DIR` | JSON export location when `json_export` is enabled |
| `EVIDENCE_BLOB_DIR` | Blob tier for oversized raw evidence |
| `API_API_KEY` | Direct OpenAI-compatible backend key |
| `BACKEND_ORDER_INGEST` | Ingest backend fallback order |
| `BACKEND_ORDER_QUERY` | Query backend fallback order |
| `BACKEND_ORDER_LINT` | Lint backend fallback order |
| `AUTOMATION_ENABLED` | Enables queue automation defaults |
| `AUTOMATION_DEFAULT_MODE` | `safe`, `balanced`, or `deep` |
| `EPISTORA_PLUGIN_DIRS` | Extra plugin search paths |
| `EPISTORA_PROMPT_PACK` | Active prompt-pack plugin ID |
| `EPISTORA_PROMPT_PROFILE` | Active prompt profile, such as `personal_learning` |

Enable JSON export alongside the vault:

```bash
ARTIFACT_SINK_IDS=markdown_vault,json_export
```

## Studio

`epistora studio` starts the local FastAPI server and serves the built React
Studio at `/studio`. Studio provides library/search views, source detail and
reader pages, queue controls, Readwise sync, pending brief compilation, catalog
snapshot import/export, chat settings, sidebar chat, and broad chat.

Set `EPISTORA_API_KEY` before exposing the API beyond localhost.

## Using Agents On The Vault

Point Claude Code, OpenCode, Codex, or another filesystem-capable agent at the
vault directory:

```bash
cd ~/epistora-vault
```

The agent should read:

1. `AGENTS.md`
2. `wiki/indexes/START_HERE.md`
3. `wiki/indexes/QUERY_PROTOCOL.md`

## Development

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run epistora help
```

Studio frontend:

```bash
cd studio
npm install
npm run build
```

## Documentation

- [Quickstart](docs/QUICKSTART.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Development](docs/DEVELOPMENT.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Roadmap](docs/ROADMAP.md)
- [ADRs](docs/adr/)

## License

[MIT](LICENSE)
