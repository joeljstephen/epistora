# Epistora

**Local-first personal knowledge compiler** that turns saved links and documents into a persistent, markdown-based, queryable knowledge base.

Epistora watches your saved bookmarks (starting with Raindrop.io), fetches the source content, compiles structured knowledge notes, extracts topics/entities/concepts, links everything together, and writes it all into an Obsidian-compatible vault. Over time, your vault compounds — topics get richer, patterns emerge across sources, and you can query your accumulated knowledge with grounded answers.

## Why Epistora?

Most "save for later" tools become link graveyards. Read-it-later apps let you highlight but don't connect ideas. RAG chatbots answer questions but don't build lasting knowledge. Epistora sits in the middle:

- **Compiles**, not just retrieves — new sources update existing topic and concept pages
- **Local-first** — your knowledge lives in markdown files you own and control
- **Obsidian-native** — open your vault in Obsidian and browse/edit alongside the automated notes
- **Queryable** — ask questions and get answers grounded in your actual saved sources
- **Inspectable** — every note has frontmatter, every claim links to a source, every action is logged
- **Multi-backend** — use OpenAI-compatible APIs, OpenCode, or Claude Code as reasoning engines
- **Automated** — run `kb worker` for hands-free background sync and maintenance

## Architecture Overview

```
Raindrop / URLs → Connectors → Compiler (LangGraph) → Vault (Markdown)
                                    ↕
                          Backend Router
                    ┌───────┼───────────┐
                    API   OpenCode   Claude Code
                                    ↕
                          SQLite (internal state)
```

- **Connectors** fetch and extract content from articles, YouTube videos, X posts, PDFs
- **Compiler** uses LangGraph workflows to analyze, extract knowledge, and produce notes
- **Backend Router** selects the best available LLM backend per task with automatic fallback
- **Vault** is a structured collection of markdown files with YAML frontmatter and `[[wikilinks]]`
- **SQLite** tracks processed sources, dedup hashes, and sync cursors (not user knowledge)

## Quick Start

```bash
# 1. Install
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Configure
cp .env.example .env
# Edit .env — set at least one backend (API key, or have opencode/claude installed)

# 3. Initialize vault
kb init

# 4. Ingest your first URL
kb ingest-url "https://lilianweng.github.io/posts/2023-06-23-agent/"

# 5. Check what was created
kb status

# 6. Query your vault
kb query "What are the main components of an AI agent?"
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `kb init` | Initialize a new knowledge vault |
| `kb ingest-url <url>` | Ingest a single URL |
| `kb sync-raindrop` | Sync recent items from Raindrop.io |
| `kb query "<question>"` | Ask a question against your vault |
| `kb lint` | Health-check the vault |
| `kb status` | Show vault and system status |
| `kb rebuild-indexes` | Rebuild all vault index files |
| `kb worker` | Run the background automation worker |
| `kb backend-status` | Show configured backends and availability |
| `kb run-sync` | Run a one-off Raindrop sync |
| `kb run-lint` | Run a one-off lint check |

## Background Worker

The `kb worker` command starts a long-running process that automatically:

- **Syncs Raindrop** at a configurable interval (default: every 20 minutes)
- **Runs lint** checks on a separate schedule (optional, default: daily)
- **Rebuilds indexes** periodically (optional, default: every 6 hours)

```bash
# Enable sync in .env
SYNC_ENABLED=true
SYNC_INTERVAL_SECONDS=1200

# Start the worker
kb worker
# Press Ctrl+C to stop gracefully
```

The worker uses file-based locking to prevent overlapping runs, and continues
safely after individual job failures.

## Multi-Backend Execution

Epistora supports three execution backends, and you can mix them per task:

### 1. Direct API Backend

Any OpenAI-compatible API endpoint. Configure with:

```env
API_API_KEY=sk-...
API_MODEL=gpt-4o-mini
# Optional: API_BASE_URL for non-OpenAI providers
```

### 2. OpenCode CLI Backend

Shells out to [OpenCode](https://github.com/opencode-ai/opencode) in non-interactive mode:

```env
OPENCODE_ENABLED=true
OPENCODE_MODEL=your-model
```

### 3. Claude Code CLI Backend

Shells out to [Claude Code](https://docs.anthropic.com/en/docs/claude-code) in print mode:

```env
CLAUDE_CODE_ENABLED=true
CLAUDE_CODE_MODEL=claude-sonnet-4-20250514
```

### Fallback Behavior

By default, for each task (ingest, query, lint) the system tries backends in order:
API → OpenCode → Claude Code.

If the first is unavailable or fails, it automatically falls back to the next.
Every fallback is logged clearly.

You can customize the order per task:

```env
BACKEND_ORDER_INGEST=opencode,api,claude_code
BACKEND_ORDER_QUERY=api,claude_code
BACKEND_ORDER_LINT=claude_code,api
```

### Mixed Backend Configuration

Use different backends/models for different tasks:

```env
# Ingest with a large-context model via API
API_MODEL_INGEST=gpt-4o
# Query with Claude Code
BACKEND_ORDER_QUERY=claude_code,api
# Lint via OpenCode
BACKEND_ORDER_LINT=opencode,api
OPENCODE_MODEL_LINT=glm-4
```

Check current backend status with:

```bash
kb backend-status
```

## API Server

```bash
uvicorn app.main:app --reload --port 8000
```

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/ingest/url` | Ingest a URL |
| POST | `/ingest/raindrop/sync` | Sync from Raindrop |
| POST | `/query` | Query the vault |
| POST | `/lint` | Run vault lint |
| GET | `/status` | System status |
| GET | `/indexes` | List index summaries |
| GET | `/automation/status` | Backend and automation status |
| POST | `/automation/run-sync` | Trigger one-off sync |
| POST | `/automation/run-lint` | Trigger one-off lint |
| POST | `/automation/rebuild-indexes` | Trigger index rebuild |

Full OpenAPI docs at `http://localhost:8000/docs`.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | For API backend | — | OpenAI API key (also used via `API_API_KEY`) |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | Default model (also used via `API_MODEL`) |
| `RAINDROP_API_TOKEN` | For sync | — | Raindrop.io API token |
| `BACKEND_ORDER_*` | No | `api,opencode,claude_code` | Fallback order per task |
| `OPENCODE_ENABLED` | No | `true` | Enable OpenCode CLI backend |
| `CLAUDE_CODE_ENABLED` | No | `true` | Enable Claude Code CLI backend |
| `SYNC_ENABLED` | No | `false` | Enable background Raindrop sync |
| `SYNC_INTERVAL_SECONDS` | No | `1200` | Sync interval |

See `.env.example` for the full list.

## Using with Obsidian

1. Run `kb init --vault /path/to/your/obsidian/vault/epistora` (or point `VAULT_PATH` to a subfolder of your existing vault)
2. Open the vault folder in Obsidian
3. Source notes, topics, entities, and concepts will appear as regular markdown with wikilinks
4. Index files provide navigation starting points
5. You can edit notes manually — the system will respect existing content on updates

## Raindrop Integration

1. Create a Raindrop.io account and get an API token from [app.raindrop.io/settings/integrations](https://app.raindrop.io/settings/integrations)
2. Set `RAINDROP_API_TOKEN` in your `.env`
3. Run `kb sync-raindrop` to ingest recent saves, or enable `SYNC_ENABLED=true` and run `kb worker`

## Vault Structure

```
knowledge_vault/
  AGENTS.md                    # Vault conventions
  inbox/raw/                   # Immutable raw captures
    articles/ videos/ threads/ pdfs/ misc/
  wiki/
    sources/                   # Compiled source notes
      articles/ videos/ threads/ pdfs/
    topics/                    # Topic pages (auto-maintained)
    entities/                  # Entity pages (people, companies, tools)
    concepts/                  # Concept pages
    synthesis/                 # Cross-source synthesis notes
    indexes/                   # Auto-generated indexes
    logs/                      # Ingest and lint logs
  outputs/
    answers/                   # Saved query answers
    digests/ reports/
```

## Testing

```bash
pytest                                    # Run all tests
pytest --cov=app --cov-report=term-missing # With coverage
pytest tests/test_backends.py -v          # Backend tests
pytest tests/test_automation.py -v        # Automation tests
```

## Limitations

- **X/Twitter extraction** is limited without API authentication — posts may be partially captured
- **YouTube transcripts** require captions to be available on the video
- **No semantic/vector search** — uses FTS5 keyword search. Semantic search is planned for v2
- **Single-user** — designed for personal use, no multi-tenancy
- **CLI backends** depend on the external binaries (`opencode`, `claude`) being installed
- **No cron expressions** — the worker uses fixed intervals only

## Future Connectors (Planned)

- Readwise Reader
- RSS feeds
- Notion
- Local folder watcher
- X/Twitter bookmarks (with API auth)
- Direct PDF/EPUB file import

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full roadmap.

## License

MIT
