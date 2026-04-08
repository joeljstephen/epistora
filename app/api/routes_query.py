from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth import require_api_key
from app.models.results import QueryResult

router = APIRouter(tags=["query"], dependencies=[Depends(require_api_key)])


class QueryRequest(BaseModel):
    question: str
    save_synthesis: bool = False


@router.post("/query", response_model=QueryResult)
async def query_vault(req: QueryRequest):
    from app.services.query_service import query_vault as _query
    return await _query(req.question, save_synthesis=req.save_synthesis)
