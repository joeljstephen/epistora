# Epistora — Open-Source Release Plan

## Overview

Transform Epistora from a personal development project into a polished, cross-platform,
open-source CLI tool that anyone can install and use with minimal friction.

## Current State Assessment

### What exists and works well
- Solid Python codebase with clear architecture (connectors, compiler, vault, automation)
- Comprehensive CLI via Typer (`kb` command) with 20+ subcommands
- FastAPI server with OpenAPI docs
- Multi-backend LLM support (API, OpenCode, Claude Code, Codex)
- Queue-based automation with cross-platform scheduler generation
- 128 tracked files, 212+ tests passing
- Existing docs: README, ARCHITECTURE, DEVELOPMENT, ROADMAP, SECURITY, LICENSE

### What needs improvement
- **CLI entry point** is `kb`, not `epistora` — confusing for a tool named Epistora
- **No setup wizard** — users must manually copy `.env.example`, edit it, run `kb init`
- **No doctor/health check** — no way to verify environment is correctly configured
- **No uv support** — only pip-based setup documented
- **Tracked junk** — log files and SQLite WAL/SHM in version control
- **Missing OSS files** — no CONTRIBUTING.md, CODE_OF_CONDUCT.md, issue/PR templates
- **.gitignore gaps** — missing patterns for logs/, test_data/, node_modules
- **Docs are developer-focused** — not approachable for non-technical users
- **No quickstart or troubleshooting guides**

## Implementation Phases

### Phase 1: Repository Hygiene
- [x] Improve `.gitignore` (logs/, test_data/, .opencode/node_modules/, Thumbs.db, etc.)
- [x] Remove tracked files that should not be committed (logs/*.log, test_data/*.db-*)
- [x] Add `.gitattributes` for consistent line endings and diff behavior
- [x] Update `.env.example` with better comments and grouping

### Phase 2: Open-Source Files
- [x] Add `CONTRIBUTING.md` — how to contribute, code style, PR process
- [x] Add `CODE_OF_CONDUCT.md` — Contributor Covenant
- [x] Add `.github/ISSUE_TEMPLATE/bug_report.md`
- [x] Add `.github/ISSUE_TEMPLATE/feature_request.md`
- [x] Add `.github/PULL_REQUEST_TEMPLATE.md`

### Phase 3: Packaging & uv
- [x] Update `pyproject.toml`:
  - Add `epistora` as the primary CLI entry point
  - Keep `kb` as a backward-compatible alias
  - Add project URLs, classifiers, authors metadata
  - Configure for uv compatibility
- [x] Set up uv workflow (`uv sync`, `uv run`)
- [x] Validate installation works via `uv tool install`

### Phase 4: CLI Refactoring
- [x] Rename internal Typer app from "kb" to "epistora"
- [x] Add `epistora setup` — interactive guided setup wizard
- [x] Add `epistora doctor` — environment and configuration health check
- [x] Add `epistora connect raindrop` — Raindrop connection helper
- [x] Add `epistora backend setup` — backend configuration helper
- [x] Add `epistora automation setup` — automation configuration helper
- [x] Add `epistora ingest latest` — quick ingest of recent bookmarks
- [x] Keep all existing commands working

### Phase 5: Setup Wizard
- [x] Interactive vault location prompt
- [x] Connector selection (Raindrop for now)
- [x] Raindrop API token input and validation
- [x] Backend selection (API, Claude Code, OpenCode, Codex)
- [x] Backend-specific configuration
- [x] Automation mode selection (safe/balanced/deep)
- [x] Optional scheduler helper generation
- [x] Config file creation/update
- [x] Vault scaffolding at chosen location
- [x] Success summary with next steps

### Phase 6: Doctor Command
- [x] Python version check
- [x] uv availability check
- [x] Config file existence and validity
- [x] Vault path existence and structure
- [x] Raindrop token presence
- [x] Backend availability (API key, CLI binaries)
- [x] Database connectivity
- [x] Automation readiness
- [x] Helpful report with recommendations

### Phase 7: Documentation Overhaul
- [x] Rewrite README.md — beginner-friendly with clear install/setup/usage
- [x] Create `docs/QUICKSTART.md`
- [x] Create `docs/TROUBLESHOOTING.md`
- [x] Update `docs/ARCHITECTURE.md`
- [x] Update `docs/DEVELOPMENT.md`

### Phase 8: Testing & Validation
- [x] Run existing test suite
- [x] Add tests for new CLI commands (setup, doctor, connect)
- [x] Validate uv workflow end-to-end
- [x] Validate CLI entry point
- [x] Fix any issues found

## Key Design Decisions

1. **`epistora` as primary command, `kb` as alias** — the tool name should match the package
2. **uv-first, pip-compatible** — uv is primary, pip still works
3. **Setup wizard creates `.env`** — no need for users to manually copy/edit
4. **Doctor validates everything** — single command to diagnose all issues
5. **Subcommand groups** — `connect`, `backend`, `automation` for organization
6. **Cross-platform from day one** — no macOS assumptions in docs or code

## User Journey After Implementation

```
# Install
uv tool install .    # or install from GitHub once the repo is accessible

# Set up everything interactively
epistora setup

# Verify configuration
epistora doctor

# Start using
epistora ingest latest
epistora automation run-pending
```

## Files Added/Modified

### New files
- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`
- `.gitattributes`
- `.github/ISSUE_TEMPLATE/bug_report.md`
- `.github/ISSUE_TEMPLATE/feature_request.md`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `app/cli/setup_wizard.py`
- `app/cli/doctor.py`
- `docs/QUICKSTART.md`
- `docs/TROUBLESHOOTING.md`
- `tests/test_cli_commands.py`

### Modified files
- `.gitignore`
- `.env.example`
- `pyproject.toml`
- `app/cli/main.py`
- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT.md`
- `docs/PLAN.md`

### Removed from tracking
- `logs/automation-stderr.log`
- `logs/automation-stdout.log`
- `test_data/app.db-shm`
- `test_data/app.db-wal`
