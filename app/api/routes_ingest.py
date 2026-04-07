from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.models.results import IngestResult

router = APIRouter(prefix="/ingest", tags=["ingest"])


class IngestUrlRequest(BaseModel):
    url: str


class SyncRaindropRequest(BaseModel):
    limit: int = 25


@router.post("/url", response_model=IngestResult)
async def ingest_url(req: IngestUrlRequest):
    from app.services.ingest_service import ingest_url as _ingest
    return await _ingest(req.url)


@router.post("/raindrop/sync", response_model=list[IngestResult])
async def sync_raindrop(req: SyncRaindropRequest):
    from app.services.ingest_service import sync_raindrop as _sync
    return await _sync(limit=req.limit)
