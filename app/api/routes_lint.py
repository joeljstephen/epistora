from __future__ import annotations

from fastapi import APIRouter

from app.models.results import LintResult

router = APIRouter(tags=["lint"])


@router.post("/lint", response_model=LintResult)
async def lint_vault():
    from app.services.lint_service import lint_vault as _lint

    return await _lint()
