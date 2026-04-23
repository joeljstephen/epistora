from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import require_api_key
from app.models.results import TopicBundleResult

router = APIRouter(tags=["topic-bundle"], dependencies=[Depends(require_api_key)])


class TopicBundleRequest(BaseModel):
    topic: str
    days: int | None = None
    source_types: list[str] = Field(default_factory=list)


@router.post(
    "/topic-bundle",
    response_model=TopicBundleResult,
    summary="Generate a grounded topic learning packet from the saved corpus",
)
async def topic_bundle(req: TopicBundleRequest):
    from app.services.topic_bundle_service import generate_topic_bundle

    try:
        return await generate_topic_bundle(
            req.topic,
            days=req.days,
            source_types=req.source_types,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
