from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.auth import require_api_key
from app.models.results import LintResult

router = APIRouter(tags=["lint"], dependencies=[Depends(require_api_key)])


@router.post("/lint", response_model=LintResult)
async def lint_vault():
    from app.services.lint_service import lint_vault as _lint

    return await _lint()
