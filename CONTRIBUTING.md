# Contributing to Epistora

Thank you for your interest in contributing to Epistora! This guide will help you
get started.

## Getting Started

### Prerequisites

- **Python 3.11+** (3.12 recommended)
- **[uv](https://docs.astral.sh/uv/)** — fast Python package manager (recommended)
- **Git**

### Development Setup

```bash
# Clone the repository
git clone https://github.com/joeljstephen/epistora.git
cd epistora

# Install dependencies with uv (recommended)
uv sync --extra dev

# Or use pip
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"

# Copy the example environment file
cp .env.example .env
# Edit .env with your configuration

# Initialize a test vault
uv run epistora init
```

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=app --cov-report=term-missing

# Run a specific test file
uv run pytest tests/test_classifier.py -v
```

All tests mock external dependencies — you don't need real API keys or CLI tools
to run the test suite.

### Packaging Smoke Test

Before opening a release-oriented PR, also validate the packaging path:

```bash
uv build
uv tool install --from . epistora --force
epistora doctor
```

### Code Style

We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
# Check for issues
uv run ruff check .

# Auto-fix issues
uv run ruff check --fix .

# Format code
uv run ruff format .
```

**Style guidelines:**
- Type hints on all function signatures
- Async-first for IO operations
- Pydantic models for data boundaries
- Max line length: 100 characters
- Follow existing patterns in the codebase

## How to Contribute

### Reporting Bugs

1. Check [existing issues](https://github.com/joeljstephen/epistora/issues) first
2. Use the **Bug Report** issue template
3. Include:
   - Your OS and Python version
   - Steps to reproduce
   - Expected vs actual behavior
   - Relevant error messages or logs

### Suggesting Features

1. Check [existing issues](https://github.com/joeljstephen/epistora/issues) and the
   [roadmap](docs/ROADMAP.md)
2. Use the **Feature Request** issue template
3. Describe the use case and why it would be valuable

### Submitting Code

1. **Fork** the repository
2. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/my-feature
   ```
3. **Make your changes** with tests
4. **Run the test suite** to make sure nothing is broken:
   ```bash
   uv run pytest
   uv run ruff check .
   ```
5. **Commit** with a clear message:
   ```bash
   git commit -m "Add support for RSS feed connector"
   ```
6. **Push** and open a **Pull Request**

### Pull Request Guidelines

- Keep PRs focused — one feature or fix per PR
- Include tests for new functionality
- Update documentation if the user-facing behavior changes
- Update `.env.example` if new configuration is added
- Reference any related issues

## Architecture Quick Reference

```
app/
  cli/           → Typer CLI commands
  api/           → FastAPI routes
  backends/      → LLM backend abstraction (API, OpenCode, Claude Code, Codex)
  automation/    → Queue-based automation system
  connectors/    → Source connectors and content extraction
  compiler/      → LangGraph workflows (ingest, lint, query)
  models/        → Pydantic data models
  vault/         → Vault read/write operations
  services/      → High-level business logic
  storage/       → SQLite persistence
  retrieval/     → Search and indexing
  utils/         → Shared utilities
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full architecture guide.
See [docs/REPO_HYGIENE.md](docs/REPO_HYGIENE.md) for commit/ignore guidance.

## Adding a New Connector

1. Create a fetcher in `app/connectors/fetchers/`
2. Implement an async function: `SourceItem` → `SourceContent`
3. Register it in `app/connectors/fetchers/__init__.py`
4. Add URL classification patterns in `app/connectors/classifier.py`
5. Write tests
6. Update docs

## Adding a New Backend

1. Create `app/backends/my_backend.py` implementing `ReasoningBackend`
2. Add `MY_BACKEND` to `BackendType` enum
3. Register in `app/backends/registry.py`
4. Add config settings to `app/config.py`
5. Write tests
6. Update `.env.example` and docs

## Questions?

Open a [discussion](https://github.com/joeljstephen/epistora/discussions) or
[issue](https://github.com/joeljstephen/epistora/issues) — we're happy to help!
