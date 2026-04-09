# Epistora

Epistora turns saved links into a local markdown knowledge vault you can browse in Obsidian and query with filesystem-capable agents.

It fetches content from sources like articles, YouTube videos, X/Twitter threads, and PDFs, then compiles:

- raw captures
- grounded source notes
- topic, entity, and concept pages
- vault indexes for humans and agents

## Quick Start

```bash
# Install from this checkout
uv tool install .

# Or for local development
# uv sync --extra dev
```

```bash
# 1. Guided setup
epistora setup

# 2. Verify config
epistora doctor

# 3. Try a small ingest first
epistora ingest latest --limit 1
```

Short alias:

```bash
eps help
```

## Everyday Commands

These are the commands most users need regularly:

| Command | What it does |
|---|---|
| `epistora setup` | Guided first-time setup |
| `epistora doctor` | Checks your environment and config |
| `epistora help` | Shows the important commands quickly |
| `epistora ingest latest --limit 1` | Ingest a small batch from Raindrop |
| `epistora ingest url <url>` | Ingest one specific source |
| `epistora status` | Shows current vault path and stats |
| `epistora vault show` | Shows which vault directory is active |
| `epistora vault use <path>` | Switches to a different vault directory |

## Changing The Vault Location

If you already ran setup and just want Epistora to use a different vault directory, you do not need to rerun setup.

```bash
epistora vault use ~/notes/my-epistora-vault
```

That command:

- updates `VAULT_PATH`
- updates the SQLite database path to the new vault
- initializes the target folder if needed

If you want to bring your current vault contents with you:

```bash
epistora vault use ~/notes/my-new-vault --copy-current
```

You can still choose the vault path during first-time setup too:

```bash
epistora setup --vault ~/notes/my-epistora-vault
```

## Help And Discovery

Epistora supports both the normal CLI help flag and a cleaner shortcut:

```bash
epistora --help
epistora help
epistora ingest --help
epistora automation --help
```

## What Ingest Looks Like

`epistora ingest latest` now shows lightweight progress so you can tell work is happening without getting flooded with logs:

- fetching the latest saved items
- moving through each item
- showing when notes are written
- printing a short done/skip/fail line per item
- ending with a compact summary

For a first smoke test, use one bookmark:

```bash
epistora ingest latest --limit 1
```

## Advanced Commands

Use these when you want more control:

| Command | What it does |
|---|---|
| `epistora connect raindrop` | Configure or update Raindrop credentials |
| `epistora backend setup` | Change LLM backend settings |
| `epistora backend status` | See which backends are available |
| `epistora sync-raindrop` | Sync from Raindrop directly |
| `epistora sync-inbox` | Sync from a configured inbox connector |
| `epistora lint` | Run vault health checks |
| `epistora rebuild-indexes` | Rebuild vault index files |
| `epistora reset-generated` | Clear generated artifacts and keep the vault shell |
| `epistora automation setup` | Configure automation |
| `epistora automation run-pending` | Run discovery, processing, and maintenance once |

## How It Works

```text
Raindrop / URLs -> fetchers -> compiler -> markdown vault
                               |
                               -> backend router (API / OpenCode / Claude Code / Codex)
```

The vault is plain markdown:

```text
your-vault/
  AGENTS.md
  raw/
  wiki/
    sources/
    topics/
    entities/
    concepts/
    indexes/
    logs/
  outputs/
```

## Using Agents On The Vault

Epistora is designed for agent-first use. Point Claude Code, OpenCode, Codex, or another filesystem-capable agent at the vault directory and ask questions there.

```bash
cd ~/epistora-vault
```

The agent should read:

1. `AGENTS.md`
2. `wiki/indexes/START_HERE.md`
3. `wiki/indexes/QUERY_PROTOCOL.md`

## Configuration

Run `epistora setup` for the guided path. If you need to edit config manually, Epistora uses environment variables.

When run from a source checkout, config is usually stored in that checkout’s `.env`.

When run as an installed tool, config is usually stored in the Epistora app directory, such as:

- Linux: `~/.config/epistora/.env`
- macOS: `~/Library/Application Support/Epistora/.env`
- Windows: `%APPDATA%\\Epistora\\.env`

Important settings:

| Variable | Description |
|---|---|
| `VAULT_PATH` | Active vault directory |
| `DATABASE_URL` | SQLite database location |
| `RAINDROP_API_TOKEN` | Raindrop token |
| `API_API_KEY` | API key for the direct API backend |
| `AUTOMATION_ENABLED` | Enables automation |
| `AUTOMATION_DEFAULT_MODE` | `safe`, `balanced`, or `deep` |

## Automation Modes

| Mode | What it does |
|---|---|
| `safe` | Fetch and archive with no LLM cost |
| `balanced` | Limited enrichment per run |
| `deep` | Full topic/entity/concept enrichment |

Examples:

```bash
epistora automation run-pending --mode safe
epistora automation run-pending --mode balanced
epistora automation run-pending --mode deep
```

## Development

```bash
git clone https://github.com/joeljstephen/epistora.git
cd epistora
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run epistora help
```

## Documentation

- [Quickstart](docs/QUICKSTART.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Development](docs/DEVELOPMENT.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Roadmap](docs/ROADMAP.md)

## License

[MIT](LICENSE)
