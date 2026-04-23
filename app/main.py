"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI

from app.api.auth import require_api_key
from app.api.routes_automation import router as automation_router
from app.api.routes_health import router as health_router
from app.api.routes_ingest import router as ingest_router
from app.api.routes_lint import router as lint_router
from app.api.routes_query import router as query_router
from app.api.routes_review import router as review_router
from app.api.routes_topic_bundle import router as topic_bundle_router
from app.api.routes_views import router as views_router
from app.config import get_settings
from app.dependencies import create_database, get_database
from app.storage.sqlite import Database
from app.vault.parser import scan_vault


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = create_database()
    app.state.db = db
    yield
    db.close()


app = FastAPI(
    title="Epistora",
    description="Local-first personal knowledge compiler API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(ingest_router)
app.include_router(query_router)
app.include_router(review_router)
app.include_router(topic_bundle_router)
app.include_router(views_router)
app.include_router(lint_router)
app.include_router(automation_router)


@app.get("/status", dependencies=[Depends(require_api_key)])
async def status(db: Database = Depends(get_database)):
    settings = get_settings()
    vault_path = Path(settings.vault_path)

    info: dict = {
        "vault_path": str(vault_path),
        "vault_exists": vault_path.exists(),
        "model": settings.openai_model,
        "api_auth_enabled": bool(settings.epistora_api_key),
        "configured_inbox_connectors": ["raindrop"] if settings.raindrop_api_token else [],
        "raindrop_configured": bool(settings.raindrop_api_token),
    }

    if vault_path.exists():
        notes = scan_vault(vault_path)
        by_type: dict[str, int] = {}
        for n in notes:
            by_type[n.note_type] = by_type.get(n.note_type, 0) + 1
        info["note_counts"] = by_type

    if settings.db_path.exists():
        from app.storage.repositories import SourceRepository

        info["processed_sources"] = SourceRepository(db).count()

    return info


@app.get("/indexes", dependencies=[Depends(require_api_key)])
async def indexes():
    settings = get_settings()
    vault_path = Path(settings.vault_path)

    if not vault_path.exists():
        return {"error": "Vault not initialized"}

    index_dir = vault_path / "wiki" / "indexes"
    if not index_dir.exists():
        return {"indexes": []}

    result = []
    for f in index_dir.glob("*.md"):
        content = f.read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        result.append(
            {
                "name": f.stem,
                "path": str(f.relative_to(vault_path)),
                "lines": len(lines),
                "preview": "\n".join(lines[:10]),
            }
        )

    return {"indexes": result}
