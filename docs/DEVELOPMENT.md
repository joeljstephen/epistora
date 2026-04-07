# Epistora — Development Guide

## Prerequisites

- Python 3.12+
- At least one of: OpenAI API key, `opencode` binary, `claude` binary
- (Optional) Raindrop.io API token

## Setup

```bash
# Clone and enter the project
cd epistora

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env with your API keys / backend config

# Initialize the vault
kb init
```

## Running

### CLI

```bash
# Initialize vault
kb init --vault ./my-vault

# Ingest a URL
kb ingest-url "https://example.com/article"

# Sync from Raindrop
kb sync-raindrop --limit 10

# Query the vault
kb query "What do I know about LangChain?"

# Run lint
kb lint

# Check status
kb status

# Rebuild indexes
kb rebuild-indexes

# Check backend availability
kb backend-status

# Run the automation worker
kb worker
```

### API Server

```bash
uvicorn app.main:app --reload --port 8000
```

Then visit http://localhost:8000/docs for the interactive API documentation.

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=term-missing

# Run specific test file
pytest tests/test_classifier.py -v

# Run backend tests
pytest tests/test_backends.py -v

# Run automation tests
pytest tests/test_automation.py -v

# Run integration tests
pytest tests/test_backend_integration.py -v
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
3. Add `MY_PROVIDER` to `BackendType` enum in `app/backends/models.py`
4. Add config settings to `app/config.py`
5. Register in `get_backend_router()` in `app/compiler/llm.py`
6. Write availability and routing tests
7. Update `.env.example`

The `generate_structured()` method has a default implementation that calls `generate()` and parses JSON from the output. Override it if your provider supports native structured output.

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
  automation/        # Background worker subsystem
    worker.py        # Main worker loop
    scheduler.py     # Interval-based scheduler
    jobs.py          # Job definitions
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
