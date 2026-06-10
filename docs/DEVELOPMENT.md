# Development

## Setup

```bash
git clone https://github.com/joeljstephen/epistora.git
cd epistora
uv sync --extra dev
cp .env.example .env
uv run epistora doctor
```

At minimum, set `VAULT_PATH` and one backend in `.env`, or run:

```bash
uv run epistora setup
```

## Common Commands

```bash
uv run epistora help
uv run epistora doctor
uv run epistora status
uv run epistora backend status
uv run epistora ingest url "https://example.com/article"
uv run epistora sync-readwise --limit 25
uv run epistora brief pending --limit 5
uv run epistora studio
```

Tests and lint:

```bash
uv run pytest
uv run ruff check .
uv run ruff format .
```

Packaging smoke test:

```bash
uv build
uv tool install --from . epistora --force
epistora doctor
```

## Studio Frontend

The Studio frontend is a React/Vite app in `studio/`. FastAPI serves built
assets from `studio/static/`.

```bash
cd studio
npm install
npm run dev
npm run build
```

After a production build, run:

```bash
uv run epistora studio
```

## Environment Resolution

Epistora loads environment files in this order:

1. `EPISTORA_ENV_FILE`, when set.
2. `.env` in the current working directory.
3. The repository `.env`, when running inside the checkout.
4. The OS-specific Epistora app config directory.

`epistora doctor` reports the loaded config path and the preferred write target.

## Runtime Data

- Main DB: configured by `DATABASE_URL`.
- Vault: configured by `VAULT_PATH`.
- Read model: `.system/state/read_model.db` inside the vault.
- JSON artifacts: `.system/exports/json/` when `json_export` is enabled.
- Source catalog snapshots: `.system/exports/source_catalog/`.
- Evidence blobs: `.system/blobs/`.

Generated runtime folders such as `data/`, `logs/`, `.system/`, `.pytest_cache/`,
`.ruff_cache/`, `.venv/`, and built distributions should not be committed.

## Backend Development

Backends implement the `ReasoningBackend` contract in `app/backends/base.py` and
are registered in `app/backends/registry.py`.

Supported built-ins:

- `api`
- `opencode`
- `claude_code`
- `codex`

Add new backend settings to `app/config.py`, update `.env.example`, register the
factory, and cover availability plus generation behavior with tests.

## Connector Development

There are two connector shapes:

- Link-only providers provide URLs and metadata. Fetchers obtain
  `SourceContent`.
- Extracted-content providers provide usable content directly. Readwise uses
  this path.

For link fetchers:

1. Add or update a fetcher under `app/connectors/fetchers/`.
2. Update classifier or dispatch logic as needed.
3. Return normalized `SourceContent`.
4. Add tests for extraction quality, fallback metadata, and failure isolation.

For inbox providers:

1. Implement the connector contract in `app/connectors/`.
2. Preserve provider refs and raw metadata.
3. Update `app/connectors/registry.py`.
4. Add CLI/API/Studio support only when the provider needs user-facing controls.

## Sink Development

Sinks consume `ArtifactBundle` objects from `app/artifacts/models.py`.

Built-ins:

- `markdown_vault`
- `json_export`

New sinks should implement `app/sinks/base.py`, register in
`app/sinks/registry.py`, and avoid compiler-specific special cases.

## Prompt Development

Prompt roots are resolved from:

1. `EPISTORA_PROMPTS_DIR`
2. active prompt-pack plugin selected by `EPISTORA_PROMPT_PACK`
3. built-in `prompts/`

Vault-local prompt overrides can live under `.system/prompts/`. Keep prompt
changes covered by `tests/test_prompts.py` when behavior changes.

## Documentation Policy

Keep documentation small and current:

- `README.md`: project overview and main command reference.
- `CONTEXT.md`: domain language and product boundaries.
- `docs/QUICKSTART.md`: first-run workflow.
- `docs/ARCHITECTURE.md`: current implementation architecture.
- `docs/DEVELOPMENT.md`: contributor workflow and extension points.
- `docs/TROUBLESHOOTING.md`: operational fixes.
- `docs/ROADMAP.md`: active direction.
- `docs/adr/`: durable architectural decisions.

Do not add long-lived planning docs unless they are ADRs. Fold implemented
feature details back into the architecture or development guide.
