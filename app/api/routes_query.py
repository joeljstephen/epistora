from __future__ import annotations

import warnings

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth import require_api_key
from app.models.results import QueryResult

router = APIRouter(tags=["query"], dependencies=[Depends(require_api_key)])


class QueryRequest(BaseModel):
    question: str
    save_synthesis: bool = False


@router.post(
    "/query",
    response_model=QueryResult,
    deprecated=True,
    summary="[DEPRECATED] Query the vault — use a direct agent instead",
    description=(
        "This endpoint is deprecated. The recommended workflow is to point "
        "Claude Code or OpenCode at the vault directory and let the agent "
        "navigate using AGENTS.md, START_HERE.md, and the index files. "
        "See AGENTS.md for the agent-first query protocol."
    ),
)
async def query_vault(req: QueryRequest):
    warnings.warn(
        "The /query API endpoint is deprecated. Use a direct agent on the vault.",
        DeprecationWarning,
        stacklevel=2,
    )
    from app.services.query_service import query_vault as _query

    return await _query(req.question, save_synthesis=req.save_synthesis)
