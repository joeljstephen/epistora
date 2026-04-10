# Repo Hygiene

This guide documents what should and should not live in the Epistora repository
when treating it as a public open-source project.

## Commit The Product, Not The Runtime State

Good candidates to commit:

- source code in `app/`
- tests in `tests/`
- prompts in `prompts/`
- templates in `knowledge_vault_template/`
- architecture and operator docs in `docs/`
- example config in `.env.example`

Do not commit generated local runtime state:

- `.env`
- `.system/`
- `knowledge_vault/`
- `data/`
- `logs/`
- large local evidence blobs
- local scheduler output

Those are intentionally ignored in [`.gitignore`](/Users/joeljacobstephen/Code/projects/epistora/.gitignore).

## Packaging Expectations

For open-source release readiness, validate:

```bash
uv build
uv run pytest
uv run ruff check .
```

If you want to smoke-test the installed CLI flow from the repo:

```bash
uv tool install --from . epistora --force
epistora doctor
```

## Config Hygiene

- keep secrets out of committed files
- prefer `.env.example` for documented settings
- use `epistora setup` for first-time config generation
- use `epistora doctor` to confirm which config file is active

## Vault Hygiene

The default user-facing durable artifact is the vault, not the repository.

- `raw/` is immutable evidence
- `wiki/` is the maintained knowledge layer
- `outputs/` is temporary scratch output
- `.system/` is internal state and should not be treated as curated knowledge

For large evidence, the visible raw note remains the stable manifest while the
heavy payload can live in `.system/blobs/`.

## Plugin Hygiene

Local plugin development should be isolated:

- keep local plugins under `plugins/` in the repo, or under `$EPISTORA_HOME/plugins`
- validate plugin manifests with the existing plugin tests
- use `EPISTORA_PLUGIN_DIRS` only for explicit local overrides
- avoid committing private plugin experiments unless they are meant to be public examples

## Docs Hygiene

When user-facing behavior changes, update:

- `README.md`
- `.env.example` if config changed
- `docs/QUICKSTART.md` for install/setup changes
- `docs/DEVELOPMENT.md` for contributor workflow changes
- `docs/ARCHITECTURE.md` if the runtime boundary changed
- `docs/PLUGIN_AUTHOR_GUIDE.md` if extension behavior changed
