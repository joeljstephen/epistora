# Contributing

## Setup

```bash
git clone https://github.com/joeljstephen/epistora.git
cd epistora
uv sync --extra dev
cp .env.example .env
uv run epistora doctor
```

You can also run the setup wizard:

```bash
uv run epistora setup
```

## Tests And Lint

```bash
uv run pytest
uv run ruff check .
uv run ruff format .
```

Run a focused test file:

```bash
uv run pytest tests/test_classifier.py -v
```

Packaging smoke test:

```bash
uv build
uv tool install --from . epistora --force
epistora doctor
```

## Pull Requests

- Keep PRs focused.
- Add or update tests for changed behavior.
- Update docs when user-facing behavior changes.
- Update `.env.example` when configuration changes.
- Prefer small, reviewable commits.

## Code Style

- Use type hints on public function boundaries.
- Keep IO paths async where the surrounding code is async.
- Use Pydantic models for structured data boundaries.
- Keep line length at 100 characters.
- Follow existing service/repository/sink patterns before adding new
  abstractions.

## Architecture Reference

See:

- [Architecture](docs/ARCHITECTURE.md)
- [Development](docs/DEVELOPMENT.md)
- [Roadmap](docs/ROADMAP.md)
- [ADRs](docs/adr/)

## Adding Connectors

For link-only sources, add or update fetcher behavior under
`app/connectors/fetchers/`, update classification/dispatch, and test extraction
quality plus failure handling.

For inbox providers, implement the connector under `app/connectors/`, preserve
provider references and tags, register it in `app/connectors/registry.py`, and
add user-facing CLI/API/Studio controls only when needed.

Extracted-content providers should normalize provider content into
`SourceContent` without forcing a native URL fetch.

## Adding Backends

1. Implement `ReasoningBackend` from `app/backends/base.py`.
2. Register the factory in `app/backends/registry.py`.
3. Add settings to `app/config.py`.
4. Update `.env.example`.
5. Add availability and generation tests.

## Adding Sinks

Sinks consume `ArtifactBundle` objects. Implement `app/sinks/base.py`, register
in `app/sinks/registry.py`, and keep compiler logic out of sink-specific code.

## Documentation Scope

Keep the docs set intentionally small. Do not add long-lived implementation
plans in `docs/` once a feature lands. Fold current behavior into
`ARCHITECTURE.md`, contributor workflow into `DEVELOPMENT.md`, and durable
decisions into ADRs.
