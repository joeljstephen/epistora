from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth import require_api_key
from app.models.results import ReviewDigestResult

router = APIRouter(tags=["review"], dependencies=[Depends(require_api_key)])


class ReviewDigestRequest(BaseModel):
    reference_date: date | None = None


@router.post(
    "/review/daily",
    response_model=ReviewDigestResult,
    summary="Generate the daily review digest",
)
async def review_daily(req: ReviewDigestRequest):
    from app.services.review_service import generate_daily_digest

    return await generate_daily_digest(reference_date=req.reference_date)


@router.post(
    "/review/weekly",
    response_model=ReviewDigestResult,
    summary="Generate the weekly review digest",
)
async def review_weekly(req: ReviewDigestRequest):
    from app.services.review_service import generate_weekly_digest

    return await generate_weekly_digest(reference_date=req.reference_date)
