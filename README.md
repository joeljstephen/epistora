# Epistora

**A local-first personal knowledge compiler** that turns your saved bookmarks into a persistent, searchable, agent-queryable knowledge base — stored as plain markdown files you own and control.

## What is Epistora?

Most "save for later" tools become link graveyards. Read-it-later apps let you highlight but don't connect ideas. RAG chatbots answer questions but don't build lasting knowledge.

Epistora sits in the middle. It:

1. **Watches your saved bookmarks** (starting with [Raindrop.io](https://raindrop.io))
2. **Fetches and extracts** the full content (articles, YouTube videos, X/Twitter threads, PDFs)
3. **Compiles structured knowledge notes** — summaries, key ideas, entities, concepts
4. **Links everything together** with topics, entities, and wikilinks
5. **Writes it all to a markdown vault** you can open in Obsidian

Over time, your vault compounds: raw evidence stays intact, wiki pages get richer, and patterns emerge across sources. You can point [Claude Code](https://docs.anthropic.com/en/docs/claude-code), [OpenCode](https://github.com/opencode-ai/opencode), or any filesystem-capable agent at the vault and ask questions grounded in your actual saved knowledge.

## Quick Start

```bash
# 1. Install from a checkout (using uv — recommended)
uv tool install .

# Or install from GitHub once the repo is accessible to you
# uv tool install git+ssh://git@github.com/joeljstephen/epistora.git

# 2. Set up everything interactively
epistora setup

# 3. Verify your configuration
epistora doctor

# 4. Ingest your latest bookmarks
epistora ingest latest
```

That's it. Your knowledge vault is now populated and ready to use.

<details>
<summary>Alternative install methods</summary>

```bash
# Install from source
git clone https://github.com/joeljstephen/epistora.git
cd epistora
uv sync --extra dev
uv run epistora setup
```

</details>

## How It Works

```
Raindrop.io / URLs → Connectors → Compiler (LangGraph) → Vault (Markdown)
                                       ↕
                             Backend Router
                       ┌───────┼──────────┐
                       API  OpenCode  Claude Code  Codex
```

- **Connectors** fetch content from articles, YouTube, X/Twitter, PDFs, and generic pages
- **Compiler** uses LangGraph workflows to analyze content and produce structured notes
- **Backend Router** selects the best available LLM backend with automatic fallback
- **Vault** is a collection of markdown files with YAML frontmatter and `[[wikilinks]]`
- **SQLite** tracks internal state (processed sources, sync cursors) — not your knowledge

## The Knowledge Vault

Your vault is a folder of markdown files organized for both human browsing and agent navigation:

```
your-vault/
  AGENTS.md                     ← Operating manual for AI agents
  raw/                          ← Immutable raw captures (articles, transcripts, threads)
  wiki/
    sources/                    ← Compiled source notes (primary evidence)
    topics/                     ← Topic pages (auto-maintained hubs)
    entities/                   ← Entity pages (people, companies, tools)
    concepts/                   ← Concept pages
    indexes/                    ← Navigation files (START_HERE, INDEX, TOPICS, etc.)
    logs/                       ← Ingest and lint logs
  outputs/                      ← Saved answers, digests, reports
```

- **Raw captures** (`raw/`) are immutable evidence — the original article text, video transcripts, thread captures
- **Source notes** (`wiki/sources/`) are compiled summaries with key ideas, entities, and wikilinks
- **Wiki pages** (`wiki/topics/`, `wiki/entities/`, `wiki/concepts/`) accumulate knowledge across sources
- **Index files** provide navigation starting points

Open the vault in [Obsidian](https://obsidian.md/) and you'll see a fully linked knowledge graph.

## Using AI Agents on Your Vault

Epistora is designed for **agent-first access**. Point Claude Code, OpenCode, or any agent at your vault directory:

```bash
cd ~/epistora-vault
# Then ask questions naturally:
# "What do I know about AI agents?"
# "Compare what different sources say about RAG vs fine-tuning"
# "What are the key takeaways from my saved YouTube videos?"
```

The agent reads `AGENTS.md`, orients using the index files, navigates to relevant source notes, and produces grounded answers with references.

## CLI Commands

### Getting Started

| Command | Description |
|---------|-------------|
| `epistora setup` | Interactive setup wizard — the best way to get started |
| `epistora doctor` | Check your environment and fix issues |
| `epistora init` | Initialize a new vault (or repair an existing one) |
| `epistora connect raindrop` | Set up Raindrop.io connection |
| `epistora backend setup` | Configure your LLM backend |

### Ingesting Content

| Command | Description |
|---------|-------------|
| `epistora ingest latest` | Ingest latest bookmarks from your connector |
| `epistora ingest url <url>` | Ingest a single URL |
| `epistora sync-raindrop` | Sync from Raindrop.io |
| `epistora sync-inbox` | Sync from any configured connector |

### Vault Maintenance

| Command | Description |
|---------|-------------|
| `epistora status` | Show vault stats and configuration |
| `epistora lint` | Run vault health checks |
| `epistora rebuild-indexes` | Rebuild all vault index files |
| `epistora backend status` | Show backend availability |
| `epistora reset-generated` | Archive and clear generated artifacts |

### Automation

| Command | Description |
|---------|-------------|
| `epistora automation run-pending` | One-shot: discover + process + maintain |
| `epistora automation setup` | Configure automation interactively |
| `epistora automation discover` | Queue new bookmarks |
| `epistora automation process-pending` | Process queued items |
| `epistora automation status` | Show queue and automation status |
| `epistora automation list-pending` | List items in the queue |
| `epistora automation retry-failed` | Retry failed items |
| `epistora automation generate-scheduler` | Generate OS scheduler config |

## Automation Modes

Epistora's automation system has three modes for cost control:

| Mode | LLM Cost | What It Does |
|------|----------|--------------|
| **safe** (default) | None | Fetch, archive raw content, write minimal source note |
| **balanced** | Capped | Safe + limited LLM enrichment per run |
| **deep** | Full | Full analysis with topic/entity/concept updates |

```bash
# Safe mode — no API costs, just capture content
epistora automation run-pending --mode safe

# Balanced — smart enrichment within budget
epistora automation run-pending --mode balanced

# Deep — full knowledge compilation
epistora automation run-pending --mode deep
```

### Cross-Platform Scheduling

Set up automatic bookmark processing on your OS:

```bash
# macOS (LaunchAgent)
epistora automation generate-scheduler --platform macos --mode safe --interval 30

# Linux (systemd)
epistora automation generate-scheduler --platform linux --mode safe --interval 30

# Windows (Task Scheduler)
epistora automation generate-scheduler --platform windows --mode safe --interval 30
```

## Multi-Backend Support

Epistora supports four LLM backends with automatic fallback:

| Backend | Type | Best For |
|---------|------|----------|
| **Direct API** | OpenAI-compatible API | Easiest setup, most reliable |
| **Claude Code** | CLI tool | If you have Claude Code installed |
| **OpenCode** | CLI tool | If you have OpenCode installed |
| **Codex** | CLI tool | If you have Codex installed |

Configure in `.env`:

```env
# API backend (easiest)
API_API_KEY=sk-your-key
API_MODEL=gpt-4o-mini

# Or use CLI backends
CLAUDE_CODE_ENABLED=true
OPENCODE_ENABLED=true
```

The system tries backends in order and falls back automatically. Customize the order per task:

```env
BACKEND_ORDER_INGEST=api,opencode,claude_code
BACKEND_ORDER_QUERY=claude_code,api
```

Check availability: `epistora backend status`

## Content Extraction

Epistora uses multi-tier fallback chains for maximum extraction quality:

- **Articles:** Trafilatura → readability-lxml → browser rendering → metadata-only
- **YouTube:** youtube-transcript-api → yt-dlp subtitles → metadata
- **X/Twitter:** Free mirrors → oEmbed → page scrape (optional: official API)
- **PDFs:** PyMuPDF text extraction
- **Generic pages:** Same article chain with broader scope

Every extraction includes quality scoring, so you know exactly what was captured.

## API Server

Epistora also includes a FastAPI server for programmatic access:

```bash
uvicorn app.main:app --reload --port 8000
```

Full OpenAPI docs at `http://localhost:8000/docs`.

## Configuration

All settings are managed via environment variables. Run `epistora setup` to create the config file interactively, or see [`.env.example`](.env.example) for the full list.

When you run Epistora from a source checkout, configuration lives in that checkout's `.env` file. When you use an installed CLI, Epistora writes config to its OS-specific app directory (for example `~/.config/epistora/.env` on Linux).

Key settings:

| Variable | Required | Description |
|----------|----------|-------------|
| `VAULT_PATH` | Yes | Where your knowledge vault lives |
| `API_API_KEY` | For API backend | OpenAI (or compatible) API key |
| `RAINDROP_API_TOKEN` | For sync | Raindrop.io API token |
| `AUTOMATION_ENABLED` | No | Enable automation (default: false) |
| `AUTOMATION_DEFAULT_MODE` | No | safe, balanced, or deep (default: safe) |

See [`.env.example`](.env.example) for all options.

## Development

```bash
# Clone and set up
git clone https://github.com/joeljstephen/epistora.git
cd epistora
uv sync --extra dev

# Run tests
uv run pytest

# Lint
uv run ruff check .

# Run the CLI
uv run epistora --help
```

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for the full development guide
and [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

## Documentation

| Document | Description |
|----------|-------------|
| [Quickstart](docs/QUICKSTART.md) | Get running in 5 minutes |
| [Architecture](docs/ARCHITECTURE.md) | System design and component overview |
| [Development](docs/DEVELOPMENT.md) | Developer setup and contribution guide |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common issues and solutions |
| [Roadmap](docs/ROADMAP.md) | What's planned next |

## Project Status

Epistora is in **beta** (v0.1.0). The core features are stable and well-tested (230+ tests), but the project is still evolving. Expect some rough edges.

**What works well:**
- Content extraction and compilation
- Multi-backend LLM support with fallback
- Queue-based automation with cost control
- Cross-platform scheduler generation
- Vault structure and agent navigation

**What's coming next:**
- More connectors (RSS, Readwise Reader, local folders)
- Semantic search with local embeddings
- Weekly digest generation
- Plugin system for custom connectors

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full roadmap.

## License

[MIT](LICENSE)
