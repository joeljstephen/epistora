from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth import require_api_key
from app.models.results import IngestResult

router = APIRouter(prefix="/ingest", tags=["ingest"], dependencies=[Depends(require_api_key)])


class IngestUrlRequest(BaseModel):
    url: str


class SyncRaindropRequest(BaseModel):
    limit: int = 25


class SyncInboxRequest(BaseModel):
    connector_id: str = "raindrop"
    limit: int = 25


@router.post("/url", response_model=IngestResult)
async def ingest_url(req: IngestUrlRequest):
    from app.services.ingest_service import ingest_url as _ingest

    try:
        return await _ingest(req.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/inbox/sync", response_model=list[IngestResult])
async def sync_inbox(req: SyncInboxRequest):
    from app.services.ingest_service import sync_inbox as _sync

    try:
        return await _sync(connector_id=req.connector_id, limit=req.limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/raindrop/sync", response_model=list[IngestResult])
async def sync_raindrop(req: SyncRaindropRequest):
    from app.services.ingest_service import sync_inbox as _sync

    try:
        return await _sync(connector_id="raindrop", limit=req.limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
