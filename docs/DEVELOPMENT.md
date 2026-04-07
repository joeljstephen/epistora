# Epistora — Development Guide

## Prerequisites

- Python 3.12+
- An OpenAI API key
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
# Edit .env with your API keys

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
```

## Project Structure

```
app/
  config.py          # Settings and environment
  main.py            # FastAPI application
  dependencies.py    # Dependency injection
  cli/               # Typer CLI
  api/               # FastAPI routes
  connectors/        # Source connectors and fetchers
  compiler/          # LangGraph workflows and LLM
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
