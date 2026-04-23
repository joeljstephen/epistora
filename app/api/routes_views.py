from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.auth import require_api_key

router = APIRouter(tags=["views"], dependencies=[Depends(require_api_key)])


@router.post("/views/rebuild")
async def rebuild_views():
    from pathlib import Path

    from app.config import get_settings
    from app.vault.index_updater import rebuild_indexes

    settings = get_settings()
    updated = rebuild_indexes(Path(settings.vault_path))
    return {"updated": updated}
