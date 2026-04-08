# Epistora

**Local-first personal knowledge compiler** that turns saved links and documents into a persistent, markdown-based, agent-queryable knowledge base.

Epistora watches your saved bookmarks (starting with Raindrop.io), fetches the
source content, preserves the raw source material, compiles structured
knowledge notes, extracts topics/entities/concepts, links everything together,
and writes it all into an Obsidian-compatible vault. Over time, your vault
compounds: raw evidence stays intact, wiki pages get richer, patterns emerge
across sources, and grounded answers can be promoted back into durable notes.

## Agent-First Query Model

Epistora is designed for **direct agent access**. Point Claude Code or OpenCode
at the vault directory and ask questions naturally. The vault is structured so
agents can navigate it effectively:

1. **`AGENTS.md`** — the operating manual for agents working with the vault
2. **`wiki/indexes/START_HERE.md`** — vault orientation map
3. **`wiki/indexes/QUERY_PROTOCOL.md`** — step-by-step query procedure
4. **Index files** — TOPICS, ENTITIES, CONCEPTS, INDEX for routing
5. **Source notes** — primary evidence, already compiled and structured
6. **Hub pages** — topic/entity/concept pages that accumulate across sources
7. **Raw captures** — immutable evidence, used only when needed

### Quick Start with Claude Code / OpenCode

```bash
# Point your agent at the vault directory
cd knowledge_vault

# Then ask questions naturally:
# "What do I know about AI agents?"
# "What are the main components of RAG?"
# "Compare what different sources say about fine-tuning vs RAG"
```

The agent will read `AGENTS.md`, orient using the index files, navigate to
relevant source notes, and produce grounded answers with note references.

### Optional: Vault Query Skill

For even better results, a skill file is included:

- **Claude Code**: `.claude/skills/vault-query.md` — loaded automatically
- **OpenCode**: `.opencode/VAULT_QUERY.md` — reference instructions

The skill provides explicit step-by-step query procedures. The vault works well
even without the skill, but the skill improves consistency.

## Why Epistora?

Most "save for later" tools become link graveyards. Read-it-later apps let you highlight but don't connect ideas. RAG chatbots answer questions but don't build lasting knowledge. Epistora sits in the middle:

- **Compiles**, not just retrieves — new sources update existing topic and concept pages
- **Preserves evidence** — raw article markdown, transcripts, thread captures, and PDF text stay separate from compiled notes
- **Local-first** — your knowledge lives in markdown files you own and control
- **Obsidian-native** — open your vault in Obsidian and browse/edit alongside the automated notes
- **Agent-first** — point Claude Code or OpenCode at the vault for grounded, source-backed answers
- **Inspectable** — every note has frontmatter, every claim links to a source, every action is logged
- **Readable** — YouTube videos become article-style notes with a `5-Minute Read` and a detailed reading version
- **Multi-backend** — use OpenAI-compatible APIs, OpenCode, Claude Code, or Codex as reasoning engines
- **Automated** — run `kb worker` for hands-free background sync and maintenance

## Architecture Overview

```
Raindrop / URLs → Connectors → Compiler (LangGraph) → Vault (Markdown)
                                    ↕
                          Backend Router
                    ┌───────┼───────────┐
                    API   OpenCode   Claude Code   Codex
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
# Edit .env — set at least one backend (API key, or have opencode/claude/codex installed)

# 3. Initialize vault
kb init

# 4. Ingest your first URL
kb ingest-url "https://lilianweng.github.io/posts/2023-06-23-agent/"

# 5. Check what was created
kb status

# 6. Query your vault using Claude Code or OpenCode
cd knowledge_vault
# Then ask: "What are the main components of an AI agent?"
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `kb init` | Initialize a new knowledge vault |
| `kb ingest-url <url>` | Ingest a single URL |
| `kb sync-inbox` | Sync recent items from a configured inbox connector |
| `kb sync-raindrop` | Sync recent items from Raindrop.io |
| `kb lint` | Health-check the vault |
| `kb status` | Show vault and system status |
| `kb rebuild-indexes` | Rebuild all vault index files |
| `kb worker` | Run the legacy background automation worker |
| `kb backend-status` | Show configured backends and availability |
| `kb run-sync` | Run a one-off Raindrop sync |
| `kb run-lint` | Run a one-off lint check |
| `kb reset-generated` | Archive and clear generated vault/state artifacts before a clean rerun |
| `kb query` | ~~Query the vault~~ (deprecated — use a direct agent instead) |
| **Automation** | |
| `kb automation discover` | Discover and queue new bookmarks |
| `kb automation process-pending` | Process queued items (--mode safe\|balanced\|deep) |
| `kb automation run-pending` | One-shot: discover + process + maintain, then exit |
| `kb automation maintain` | Run maintenance tasks (lint, index rebuild) |
| `kb automation status` | Show queue counts, last run, backend availability |
| `kb automation list-pending` | List queued items pending processing |
| `kb automation retry-failed` | Retry items with retryable failures |
| `kb automation generate-scheduler` | Generate OS scheduler config files |

Use `--force` with `kb ingest-url`, `kb sync-inbox`, or `kb sync-raindrop` to
re-run ingest for already-seen sources without deleting existing vault state.

## Automation

Epistora provides two automation approaches: queue-based (recommended) and legacy interval-based worker.

### Queue-Based Automation (recommended)

The queue-based system separates discovery from processing and supports cost-aware modes:

```bash
# One-shot: discover + process + maintain, then exit
kb automation run-pending --mode safe

# Or run steps individually:
kb automation discover                          # Queue new bookmarks
kb automation process-pending --mode balanced    # Process with capped LLM
kb automation maintain --lint --rebuild          # Run maintenance

# Check status
kb automation status
```

#### Automation Modes

| Mode | LLM Cost | Behavior |
|------|----------|----------|
| **safe** (default) | None | Fetch, archive raw content, write minimal source note |
| **balanced** | Capped | Safe + limited LLM enrichment per run |
| **deep** | Full | Full ingest graph with topic/entity/concept updates |

#### Cross-Platform Scheduling

The one-shot `run-pending` command is designed for OS schedulers:

```bash
# Generate scheduler config for your platform
kb automation generate-scheduler --platform macos --mode safe --interval 30
kb automation generate-scheduler --platform linux --mode safe --interval 30
kb automation generate-scheduler --platform windows --mode safe --interval 30
```

This generates LaunchAgent plists, systemd units, or Task Scheduler XML files.

### Legacy Background Worker

The `kb worker` command starts a long-running process that automatically:

- **Syncs the configured inbox connector** at a configurable interval (default: every 20 minutes)
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

Epistora supports four execution backends, and you can mix them per task:

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

Epistora sends the full OpenCode prompt as a single `opencode run ... "<prompt>"`
argument. That keeps execution simple, but very large prompts are still subject
to OS argv limits.

### 3. Claude Code CLI Backend

Shells out to [Claude Code](https://docs.anthropic.com/en/docs/claude-code) in print mode:

```env
CLAUDE_CODE_ENABLED=true
CLAUDE_CODE_MODEL=claude-sonnet-4-20250514
```

### 4. Codex CLI Backend

Shells out to `codex exec` in non-interactive mode:

```env
CODEX_ENABLED=true
CODEX_MODEL=gpt-5
```

### Fallback Behavior

By default, for each task (ingest, query, lint) the system tries backends in order:
API → OpenCode → Claude Code → Codex.

If the first is unavailable or fails, it automatically falls back to the next.
Every fallback is logged clearly.

You can customize the order per task:

```env
BACKEND_ORDER_INGEST=opencode,api,claude_code
BACKEND_ORDER_QUERY=api,claude_code,codex
BACKEND_ORDER_LINT=claude_code,codex,api
```

Unknown backend tokens are ignored with a warning by default. Set
`BACKEND_ORDER_STRICT=true` to fail fast on typos.

### Mixed Backend Configuration

Use different backends/models for different tasks:

```env
# Ingest with a large-context model via API
API_MODEL_INGEST=gpt-4o
# Query with Claude Code
BACKEND_ORDER_QUERY=claude_code,api
# Or switch query to Codex
BACKEND_ORDER_QUERY=codex,claude_code,api
CODEX_MODEL_QUERY=gpt-5
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
| POST | `/ingest/inbox/sync` | Sync from a configured inbox connector |
| POST | `/ingest/raindrop/sync` | Sync from Raindrop |
| POST | `/query` | ~~Query the vault~~ (deprecated) |
| POST | `/lint` | Run vault lint |
| GET | `/status` | System status |
| GET | `/indexes` | List index summaries |
| GET | `/automation/status` | Backend, queue, and automation status |
| POST | `/automation/discover` | Discover and queue new bookmarks |
| POST | `/automation/process-pending` | Process queued items |
| POST | `/automation/run-pending` | One-shot: discover + process + maintain |
| POST | `/automation/run-sync` | Trigger one-off sync (legacy) |
| POST | `/automation/run-lint` | Trigger one-off lint |
| POST | `/automation/rebuild-indexes` | Trigger index rebuild |

Full OpenAPI docs at `http://localhost:8000/docs`.

If `EPISTORA_API_KEY` is set, the sensitive routes above require
`Authorization: Bearer <token>`. `/health` remains public.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | For API backend | — | OpenAI API key (also used via `API_API_KEY`) |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | Default model (also used via `API_MODEL`) |
| `EPISTORA_API_KEY` | No | — | Optional bearer token for sensitive API routes |
| `RAINDROP_API_TOKEN` | For sync | — | Raindrop.io API token |
| `BACKEND_ORDER_*` | No | `api,opencode,claude_code,codex` | Fallback order per task |
| `BACKEND_ORDER_STRICT` | No | `false` | Fail on unknown backend tokens instead of warning |
| `OPENCODE_ENABLED` | No | `true` | Enable OpenCode CLI backend |
| `CLAUDE_CODE_ENABLED` | No | `true` | Enable Claude Code CLI backend |
| `CODEX_ENABLED` | No | `true` | Enable Codex CLI backend |
| `SYNC_ENABLED` | No | `false` | Enable background inbox sync (legacy worker) |
| `SYNC_INTERVAL_SECONDS` | No | `1200` | Sync interval (legacy worker) |
| `AUTOMATION_ENABLED` | No | `false` | Enable queue-based automation |
| `AUTOMATION_DEFAULT_MODE` | No | `safe` | Default mode: safe, balanced, deep |
| `AUTOMATION_PROCESS_LIMIT` | No | `10` | Max items processed per run |
| `AUTOMATION_DEEP_ENRICH_LIMIT_PER_RUN` | No | `3` | Max LLM enrichments per run |
| `AUTOMATION_DEEP_ENRICH_LIMIT_PER_DAY` | No | `20` | Max LLM enrichments per day |
| `AUTOMATION_RETRY_MAX_ATTEMPTS` | No | `5` | Max retry attempts before permanent failure |

See `.env.example` for the full list.

## Using with Obsidian

1. Run `kb init --vault /path/to/your/obsidian/vault/epistora` (or point `VAULT_PATH` to a subfolder of your existing vault)
2. Open the vault folder in Obsidian
3. Source notes, topics, entities, and concepts will appear as regular markdown with wikilinks
4. Index files provide navigation starting points
5. You can edit notes manually — the system will respect existing content on updates

## Using with Claude Code

1. Build your vault: `kb ingest-url <url>` or `kb sync-raindrop`
2. Point Claude Code at the vault: `cd knowledge_vault`
3. Ask questions naturally — Claude Code reads `AGENTS.md` and navigates
4. The `.claude/skills/vault-query.md` skill improves query consistency

## Using with OpenCode

1. Build your vault: `kb ingest-url <url>` or `kb sync-raindrop`
2. Point OpenCode at the vault: `cd knowledge_vault`
3. Ask questions naturally — OpenCode reads `AGENTS.md` and the index files
4. The `.opencode/VAULT_QUERY.md` file provides additional guidance

## Raindrop Integration

1. Create a Raindrop.io account and get an API token from [app.raindrop.io/settings/integrations](https://app.raindrop.io/settings/integrations)
2. Set `RAINDROP_API_TOKEN` in your `.env`
3. Run `kb sync-raindrop` (or `kb sync-inbox --connector raindrop`) to ingest recent saves, or enable `SYNC_ENABLED=true` and run `kb worker`

## Vault Structure

```
knowledge_vault/
  AGENTS.md                    # Agent operating manual
  .claude/skills/vault-query.md # Claude Code query skill
  .opencode/VAULT_QUERY.md     # OpenCode agent instructions
  inbox/raw/                   # Immutable raw captures
    articles/                  # Readable article archives
    videos/                    # Transcript captures + video metadata
    threads/                   # Raw thread captures
    pdfs/ misc/
  wiki/
    sources/                   # Compiled source notes (primary evidence)
      articles/ videos/ threads/ pdfs/ misc/
    topics/                    # Topic pages (auto-maintained hubs)
    entities/                  # Entity pages (people, companies, tools)
    concepts/                  # Concept pages
    synthesis/                 # Cross-source synthesis notes
    indexes/                   # Navigation files
      START_HERE.md            # Vault orientation map
      QUERY_PROTOCOL.md        # Standard query procedure
      INDEX.md                 # Full vault index with stats
      TOPICS.md                # Topic pages list
      ENTITIES.md              # Entity pages list
      CONCEPTS.md              # Concept pages list
    logs/                      # Ingest and lint logs
  outputs/
    answers/                   # Saved query answers
    digests/ reports/
```

## Resetting And Re-running

To clear only generated vault artifacts and generated internal state while
keeping source code and `AGENTS.md` intact:

```bash
kb reset-generated --yes --archive
kb sync-raindrop --limit 30
```

This archives the previous generated raw/wiki/output/state files under
`.system/archives/` before rebuilding from a clean slate.

## Testing

```bash
pytest                                    # Run all tests
pytest --cov=app --cov-report=term-missing # With coverage
pytest tests/test_backends.py -v          # Backend tests
pytest tests/test_automation.py -v        # Automation tests
```

## summarize.sh Integration

Epistora can optionally use `summarize` as an extraction helper at the
`SourceContent` boundary. It does **not** replace the ingest graph, SQLite
dedup/state, vault writer, analysis schema, or query pipeline.

- Install summarize separately and make sure `summarize --version` works on your `PATH`
- Enable it explicitly in `.env`; the integration is disabled by default
- Epistora shells out to the CLI directly today; daemon settings are reserved for a later phase

```env
SUMMARIZE_ENABLED=true
SUMMARIZE_BINARY=summarize
SUMMARIZE_TIMEOUT_SECONDS=180

SUMMARIZE_USE_FOR_YOUTUBE_PRIMARY=true
SUMMARIZE_USE_FOR_ARTICLE_FALLBACK=true
SUMMARIZE_USE_FOR_GENERIC_FALLBACK=true
SUMMARIZE_USE_FOR_X_FALLBACK=true

SUMMARIZE_PREFER_MARKDOWN=true
SUMMARIZE_ALLOW_DAEMON=false
SUMMARIZE_DAEMON_URL=
```

## Content Extraction

Epistora uses multi-tier fallback chains for each source type to maximize extraction quality:

### Articles
1. **Trafilatura** (primary) — best-in-class Python article extraction
2. **readability-lxml** (fallback) — alternative extraction when trafilatura yields thin content
3. **summarize CLI** (optional fallback) — only attempted when the local extraction is clearly weak
4. **Browser rendering** (optional) — Playwright-based for JS-heavy pages
5. **Metadata-only** — OG tags, title, description when all else fails

For article sources, Epistora writes two separate artifacts:

- a clean readable markdown archive in `inbox/raw/articles/`
- a compiled source note in `wiki/sources/articles/`

Raw article archives are preserved as readable markdown with metadata at the
top and without AI-written summary text mixed into the body.

### Generic Pages
1. **Trafilatura** (primary) — best-effort main-content extraction
2. **readability-lxml** (fallback) — useful for docs pages and mixed layouts
3. **summarize CLI** (optional fallback) — used only when the generic extractor stays weak
4. **Browser rendering** (optional) — Playwright fallback for JS-heavy pages
5. **Metadata-only** — OG tags, title, description when body extraction fails

If a Raindrop bookmark is tagged `article`, Epistora treats that tag as a
strong signal and routes the bookmark through the article-preservation path.

### YouTube
1. **summarize CLI** (optional primary) — transcript/media extraction and first-pass markdown capture
2. **youtube-transcript-api** — prefers manual English, then auto, then any language
3. **yt-dlp subtitles** — subtitle-only extraction (no video download)
4. **Metadata/noembed** — title, channel, description when no transcript available
5. **Local ASR hook** — extension point for Whisper (not active by default)

When a transcript is available, the raw transcript is preserved in
`inbox/raw/videos/`, and the compiled source note in `wiki/sources/videos/`
includes:

- a short summary
- a `5-Minute Read`
- a detailed article-style reading note
- transcript status, caption type, extraction source, and transcript quality
- key ideas, examples, takeaways, quotes, and follow-up questions
- an explicit recommendation on whether the full video is still worth watching

The raw transcript capture stays immutable once written; later force-reruns
update the compiled wiki layer and logs, not the evidence layer.

### X/Twitter
1. **Official X API** — full post + thread reconstruction (optional, requires bearer token)
2. **fxtwitter/vxtwitter** — free mirror APIs with thread and article expansion
3. **oEmbed/noembed** — embedded tweet text extraction
4. **summarize CLI** (optional fallback) — only after X-specific methods stay weak
5. **Page scrape** — OG tags and visible text
6. **Browser rendering** (optional) — Playwright fallback

### PDFs
- **PyMuPDF** text extraction with metadata from PDF properties

Every extraction result includes `extraction_quality` (`full`, `mostly_full`, `partial`, `metadata_only`, `failed`), the method used, the full fallback chain attempted, and detailed notes.

Weak-extraction detection is explicit and test-covered. summarize is only
invoked when the earlier extractor returns too little body text, too few
paragraphs, teaser-like output, or metadata-only content.

Epistora also normalizes extracted topic/entity/concept names against existing
vault pages where possible so re-ingest runs are less likely to fragment the
wiki with obvious spelling or formatting variants.

## Validation Notes

The latest-bookmark validation for this upgrade was run on **April 8, 2026**
against the newest Raindrop item at the time:

- `https://youtube.com/watch?v=aFcVKzfkJPk&si=0X3V7ZbXMl5m-3ib`
- title: `Claude Mythos and the end of software`
- source type: `youtube`

The validation run used a force re-ingest of that single bookmark and produced:

- an updated raw transcript capture in `inbox/raw/videos/`
- a richer compiled source note with transcript status, `5-Minute Read`, and
  article-style detail in `wiki/sources/videos/`
- updated topic/entity/concept pages, indexes, and ingest logs

No generated vault documents were deleted or reset during this validation.

### Optional X API Support

X extraction works without any API credentials using free mirror endpoints. If you want higher-quality extraction with thread reconstruction, configure the official X API:

```env
X_API_ENABLED=true
X_API_BEARER_TOKEN=your-bearer-token
```

### Browser-Rendered Fallback

For JS-heavy pages that static extraction can't handle:

```bash
pip install playwright && playwright install chromium
```

```env
BROWSER_FALLBACK_ENABLED=true
```

## Limitations

- **summarize integration is CLI-only today** — `SUMMARIZE_ALLOW_DAEMON` and `SUMMARIZE_DAEMON_URL` are reserved for future support
- **summarize is disabled by default** — enable it explicitly if you want it in the extraction path
- **YouTube transcripts** require captions to be available on the video
- **X/Twitter free extraction** may miss some thread continuity — configure X API for best results
- **Browser fallback** requires separate Playwright installation
- **PDF OCR** not supported — scanned/image-only PDFs yield limited text
- **No semantic/vector search** — uses FTS5 keyword search. Semantic search is planned for v2
- **Single-user** — designed for personal use, no multi-tenancy
- **CLI backends** depend on the external binaries (`opencode`, `claude`) being installed
- **LLM-generated ontology** can still need manual cleanup for semantically similar
  but not obviously identical topics (for example, two different phrasings that
  do not collapse to the same slug)

## Future Connectors (Planned)

- Readwise Reader
- RSS feeds
- Notion
- Local folder watcher
- Direct PDF/EPUB file import

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full roadmap.

## License

MIT
