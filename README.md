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

## Architecture Overview

```
Raindrop / URLs → Connectors → Compiler (LangGraph) → Vault (Markdown)
                                    ↕
                              OpenAI LLM
                                    ↕
                          SQLite (internal state)
```

- **Connectors** fetch and extract content from articles, YouTube videos, X posts, PDFs
- **Compiler** uses LangGraph workflows to analyze, extract knowledge, and produce notes
- **Vault** is a structured collection of markdown files with YAML frontmatter and `[[wikilinks]]`
- **SQLite** tracks processed sources, dedup hashes, and sync cursors (not user knowledge)

## Quick Start

```bash
# 1. Install
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Configure
cp .env.example .env
# Edit .env — at minimum set OPENAI_API_KEY

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

Full OpenAPI docs at `http://localhost:8000/docs`.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes | — | OpenAI API key |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | Model to use |
| `RAINDROP_API_TOKEN` | For sync | — | Raindrop.io API token |
| `RAINDROP_COLLECTION_ID` | No | `0` | Raindrop collection (0 = all) |
| `VAULT_PATH` | No | `./knowledge_vault` | Path to the knowledge vault |
| `DATABASE_URL` | No | `sqlite:///./data/app.db` | SQLite database path |

## Using with Obsidian

1. Run `kb init --vault /path/to/your/obsidian/vault/epistora` (or point `VAULT_PATH` to a subfolder of your existing vault)
2. Open the vault folder in Obsidian
3. Source notes, topics, entities, and concepts will appear as regular markdown with wikilinks
4. Index files provide navigation starting points
5. You can edit notes manually — the system will respect existing content on updates

## Raindrop Integration

1. Create a Raindrop.io account and get an API token from [app.raindrop.io/settings/integrations](https://app.raindrop.io/settings/integrations)
2. Set `RAINDROP_API_TOKEN` in your `.env`
3. Run `kb sync-raindrop` to ingest recent saves

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
pytest tests/test_classifier.py -v        # Specific file
```

## v1 Limitations

- **X/Twitter extraction** is limited without API authentication — posts may be partially captured
- **YouTube transcripts** require captions to be available on the video
- **No semantic/vector search** — v1 uses FTS5 keyword search. Semantic search is planned for v2
- **Single-user** — designed for personal use, no multi-tenancy
- **Raindrop only** — future versions will add Readwise Reader, RSS, Notion, and more

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
