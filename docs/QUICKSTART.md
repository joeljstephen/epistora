# Quickstart

Use this path for a local checkout.

## Prerequisites

- Python 3.11 or newer.
- `uv`.
- At least one reasoning backend:
  - `API_API_KEY` for an OpenAI-compatible API, or
  - `opencode`, `claude`, or `codex` installed on your PATH.
- Optional connector credentials:
  - `READWISE_API_TOKEN` for Readwise Reader import.
  - `RAINDROP_API_TOKEN` for Raindrop ingest.

## Install

```bash
git clone https://github.com/joeljstephen/epistora.git
cd epistora
uv sync --extra dev
```

Installed tool path:

```bash
uv tool install .
```

## Configure

Guided setup:

```bash
uv run epistora setup
```

Installed CLI:

```bash
epistora setup
```

Manual setup from a checkout:

```bash
cp .env.example .env
```

Then set at least `VAULT_PATH` and one backend. Add connector tokens if you want
Readwise or Raindrop.

Verify the active config:

```bash
uv run epistora doctor
```

## Ingest One URL

```bash
uv run epistora ingest url "https://example.com/article"
```

The link-only URL path fetches content, runs compiler analysis through the
backend router, writes raw evidence, renders vault notes, and records processing
state.

## Import Readwise And Compile Briefs

Configure the connector:

```bash
uv run epistora connect readwise
```

Import Readwise items into the source catalog:

```bash
uv run epistora sync-readwise --limit 25
```

Compile pending imported sources:

```bash
uv run epistora brief pending --limit 5
```

Readwise import itself does not call an LLM. Brief compilation is the LLM
boundary.

## Ingest Raindrop

Configure the connector:

```bash
uv run epistora connect raindrop
```

Run a small smoke test:

```bash
uv run epistora ingest latest --limit 1
```

## Open Studio

```bash
uv run epistora studio
```

Studio is served by the local FastAPI app at `/studio`. It includes Library,
Search, Queue, Settings, source reader pages, Readwise sync, brief compilation,
snapshot tools, and chat surfaces.

## Use The Vault

Open the configured vault in Obsidian or point an agent at it:

```bash
cd ~/epistora-vault
```

Start with:

1. `AGENTS.md`
2. `wiki/indexes/START_HERE.md`
3. `wiki/indexes/QUERY_PROTOCOL.md`

## Useful Follow-Up Commands

```bash
uv run epistora status
uv run epistora backend status
uv run epistora views rebuild
uv run epistora topic-bundle "agentic AI"
uv run epistora review daily
uv run epistora automation run-pending --mode safe
uv run epistora automation run-personal-learning --mode balanced
```
