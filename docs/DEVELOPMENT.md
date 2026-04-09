# Epistora — Development Guide

## Prerequisites

- **Python 3.11+** (3.12 recommended)
- **[uv](https://docs.astral.sh/uv/)** — fast Python package manager (recommended)
- At least one of: OpenAI API key, `opencode` binary, `claude` binary
- (Optional) Raindrop.io API token
- (Optional) `summarize` binary if you want summarize-backed extraction enabled

## Setup

### Using uv (recommended)

```bash
# Clone and enter the project
git clone https://github.com/joeljstephen/epistora.git
cd epistora

# Install all dependencies (including dev)
uv sync --extra dev

# Configure environment
cp .env.example .env
# Edit .env with your API keys / backend config

# Or run the interactive setup wizard
uv run epistora setup
```

### Using pip

```bash
cd epistora
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
cp .env.example .env
```

## Running

### CLI

```bash
# Interactive setup (recommended for first-time)
epistora setup

# Check environment health
epistora doctor

# Initialize vault
epistora init --vault ./my-vault

# Ingest a URL
epistora ingest url "https://example.com/article"

# Ingest latest bookmarks
epistora ingest latest

# Re-run ingest without clearing prior vault state
epistora ingest url --force "https://example.com/article"

# Sync from Raindrop
epistora sync-raindrop --limit 10

# Reset generated vault artifacts before a clean replay
epistora reset-generated --yes --archive

# Run lint
epistora lint

# Check status
epistora status

# Rebuild indexes
epistora rebuild-indexes

# Check backend availability
epistora backend status

# Configure backend interactively
epistora backend setup

# Connect to Raindrop
epistora connect raindrop

# --- Queue-Based Automation ---

# Configure automation interactively
epistora automation setup

# Discover and queue new bookmarks
epistora automation discover

# Process pending items (safe mode — no LLM cost)
epistora automation process-pending --mode safe

# Process with AI enrichment (capped)
epistora automation process-pending --mode balanced --limit 5

# One-shot end-to-end: discover + process + maintain
epistora automation run-pending --mode safe

# Check automation status
epistora automation status

# List pending queue items
epistora automation list-pending

# Retry failed items
epistora automation retry-failed --mode balanced

# Run maintenance tasks
epistora automation maintain --lint --rebuild

# Generate OS scheduler helpers
epistora automation generate-scheduler --platform macos --mode safe --interval 30
```

Note: If running from source, prefix commands with `uv run` (e.g., `uv run epistora setup`).
The short alias is `eps`.

### Automation Modes

| Mode | LLM Usage | Description |
|------|-----------|-------------|
| `safe` | None | Fetch + archive only. No LLM cost. Good for default scheduled runs. |
| `balanced` | Capped | Safe mode + limited LLM enrichment per run. Controlled cost. |
| `deep` | Full | Full ingest graph with topic/entity/concept updates. Opt-in. |

### Cross-Platform Scheduling

The `epistora automation run-pending` command is the primary building block for OS schedulers. It runs one-shot, is idempotent, and exits cleanly.

```bash
# Generate scheduler configs for your OS
epistora automation generate-scheduler --platform all --mode safe --interval 30
```

This generates:
- macOS: LaunchAgent plist
- Linux: systemd service + timer
- Windows: Task Scheduler XML
- Instructions: SCHEDULING.md

### Querying the Vault (Agent-First)

The recommended way to query the vault is to use Claude Code or OpenCode
directly on the vault directory:

```bash
cd knowledge_vault

# Then ask questions naturally using your agent
# "What do I know about LangChain?"
# "What are the main takeaways from the AI agent video?"
```

The agent reads `AGENTS.md` and navigates the vault using the index files.
See `wiki/indexes/START_HERE.md` and `wiki/indexes/QUERY_PROTOCOL.md` for
the navigation procedure.

The legacy `epistora query` command is deprecated but still functional.

### API Server

```bash
uvicorn app.main:app --reload --port 8000
```

Then visit http://localhost:8000/docs for the interactive API documentation.

## Testing

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=app --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_classifier.py -v

# Run backend tests
uv run pytest tests/test_backends.py -v

# Run queue-based automation tests
uv run pytest tests/test_queue_automation.py -v

# Run CLI tests
uv run pytest tests/test_cli_commands.py -v
```

### Testing Without Real Backends

All tests mock external dependencies. You don't need a real OpenAI key, `opencode` binary, or `claude` binary to run the test suite.

**Mocking the backend router:**

```python
from unittest.mock import AsyncMock, patch
from app.backends.models import BackendResponse, BackendType

# Mock run_structured for graph node tests
with patch(
    "app.compiler.ingest_graph.run_structured",
    new_callable=AsyncMock,
    return_value=BackendResponse(
        text='{"summary": "test"}',
        success=True,
        backend_used=BackendType.API,
        model_used="mock",
    ),
):
    result = await some_graph_node(state)
```

**Mocking CLI backend binaries:**

```python
from unittest.mock import patch

# Pretend opencode is installed
with patch("shutil.which", return_value="/usr/local/bin/opencode"):
    backend = OpenCodeCliBackend(enabled=True)
    assert backend.is_available() is True

# Pretend it's missing
with patch("shutil.which", return_value=None):
    backend = OpenCodeCliBackend(enabled=True)
    assert backend.is_available() is False
```

### Testing summarize Integration

summarize-backed extraction is fully mockable; tests do not require the real
binary or network access.

- Wrapper tests patch `subprocess.run` in `app/connectors/fetchers/summarize_cli.py`
- Fetcher integration tests patch `summarize_extract_url`, `summarize_is_available`, and `summarize_result_to_source_content`
- Existing fetcher tests stay hermetic because summarize is disabled by default unless the test opts in

Example:

```python
from unittest.mock import AsyncMock, patch

with patch("app.connectors.fetchers.youtube.summarize_is_available", return_value=True), patch(
    "app.connectors.fetchers.youtube.summarize_extract_url",
    new_callable=AsyncMock,
) as mock_extract:
    mock_extract.return_value = SummarizeResult(success=False, provider_notes="mock failure")
    result = await fetch_youtube(item)
```

### Local summarize Debugging

To validate the live CLI path locally:

```bash
summarize --version
epistora ingest url "https://www.youtube.com/watch?v=..."
```

Useful settings while debugging:

```env
SUMMARIZE_ENABLED=true
SUMMARIZE_TIMEOUT_SECONDS=180
SUMMARIZE_USE_FOR_YOUTUBE_PRIMARY=true
SUMMARIZE_USE_FOR_ARTICLE_FALLBACK=true
SUMMARIZE_USE_FOR_GENERIC_FALLBACK=true
SUMMARIZE_USE_FOR_X_FALLBACK=true
```

Inspect `extraction_method`, `extraction_fallback_chain`, `extraction_notes`,
and `raw_metadata["summarize"]` in the resulting `SourceContent` or raw note
frontmatter to confirm which path won.

**Testing the router's fallback behavior:**

```python
# Create mock backends with controlled availability
api = _make_mock_backend(available=False)
oc = _make_mock_backend(available=True, response_text="from opencode")
router = BackendRouter(
    backends={BackendType.API: api, BackendType.OPENCODE: oc},
    default_order=[BackendType.API, BackendType.OPENCODE],
)
# Router will skip API and use OpenCode
selected, reasons = router.select_backend(TaskName.INGEST)
assert selected is oc
```

### Developing New Providers

To add a new backend provider:

1. Create `app/backends/my_provider.py`
2. Subclass `ReasoningBackend` and implement:
   - `generate(request) -> BackendResponse`
   - `is_available(task) -> bool`
   - `describe(task) -> BackendDescriptor`
3. Add `MY_PROVIDER` to `BackendType` if you want a first-class built-in identifier
4. Add config settings to `app/config.py`
5. Register the factory in `app/backends/registry.py`
6. Write availability and routing tests
7. Update `.env.example`

The `generate_structured()` method has a default implementation that calls `generate()` and parses JSON from the output. Override it if your provider supports native structured output.

## Resetting Generated State

Use `epistora reset-generated --yes --archive` when you want to:

- archive the current generated raw/wiki/output/state artifacts
- clear processed-source and sync cursor state
- rerun the latest Raindrop items from a clean generated vault

This does not touch application source code or the vault operating manual.

Use `--force` on ingest commands when you want to recompile an existing source
in place without deleting generated vault content first. This is the preferred
workflow for validating prompt/template upgrades against a single known source.
The editable prompt files live under `prompts/`, with optional source-specific
overrides such as `prompts/ingest/source_analysis.youtube.md`.

## Latest-Bookmark Validation

The Phase 10 knowledge-quality upgrade was validated on **April 8, 2026** by:

1. Fetching the latest Raindrop bookmark directly from the configured inbox.
2. Running the ingest graph on that single item with `force_reingest=True`.
3. Inspecting the generated raw capture, source note, topic pages, indexes,
   and ingest log.
4. Fixing workflow issues found during that run:
   - Codex structured-output schema normalization
   - topic/entity/concept placeholder replacement on update
   - multi-link merge preservation in topic/entity/concept pages
   - topic/entity/concept name normalization against existing vault pages

This validation intentionally did **not** reset or delete the existing vault.

## Project Structure

```
app/
  config.py          # Settings and environment
  main.py            # FastAPI application
  dependencies.py    # Dependency injection
  cli/               # Typer CLI
  api/               # FastAPI routes (+ automation endpoints)
  backends/          # Multi-backend LLM abstraction
    base.py          # Abstract ReasoningBackend
    router.py        # BackendRouter with fallback
    direct_api.py    # OpenAI-compatible API backend
    opencode_cli.py  # OpenCode CLI backend
    claude_code_cli.py # Claude Code CLI backend
    models.py        # Backend data models
  automation/        # Automation subsystem
    models.py        # Queue and run data models
    queue_store.py   # Durable SQLite queue persistence
    discovery.py     # Bookmark discovery and staging
    processing.py    # Mode-aware processing pipeline
    runner.py        # One-shot automation runner
    scheduler_helpers.py  # Cross-platform scheduler generation
    worker.py        # Legacy interval-based worker loop
    scheduler.py     # Legacy interval-based scheduler
    jobs.py          # Legacy job definitions
    locks.py         # File-based locking
  connectors/        # Source connectors and fetchers
  compiler/          # LangGraph workflows and LLM routing
  models/            # Pydantic data models
  retrieval/         # Search and indexing
  vault/             # Vault read/write operations
  services/          # High-level business logic
  storage/           # SQLite persistence
  utils/             # Shared utilities
```

## Adding a New Connector

1. Create a fetcher in `app/connectors/fetchers/`
2. Implement an async function that takes `SourceItem` and returns `SourceContent`
3. Register it in `app/connectors/fetchers/__init__.py`
4. Add URL classification patterns if needed in `app/connectors/classifier.py`
5. Write tests

## Code Style

- Ruff for linting (`ruff check .`)
- Type hints everywhere
- Async-first for IO operations
- Pydantic models for all data boundaries
