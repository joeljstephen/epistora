from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import require_api_key
from app.config import get_settings
from app.dependencies import get_database
from app.models.studio import (
    StudioBriefCompileResponse,
    StudioEnqueueActionRequest,
    StudioJobListResponse,
    StudioKnowledgeDetailResponse,
    StudioKnowledgeListResponse,
    StudioManualAddRequest,
    StudioManualAddResponse,
    StudioPendingBriefRequest,
    StudioProcessingJobResponse,
    StudioProcessJobsResponse,
    StudioReadwiseSyncRequest,
    StudioReadwiseSyncResponse,
    StudioSearchResponse,
    StudioSnapshotExportResponse,
    StudioSnapshotImportRequest,
    StudioSnapshotImportResponse,
    StudioSourceDetail,
    StudioSourceListResponse,
    StudioSourceReaderResponse,
    StudioStatsResponse,
)
from app.services.studio_service import (
    KNOWLEDGE_NOTE_TYPES,
    compile_pending_briefs_for_studio,
    compile_source_brief_for_studio,
    default_snapshot_path,
    enqueue_source_action,
    get_knowledge_detail,
    get_studio_source_detail,
    get_studio_source_reader,
    get_studio_stats,
    list_knowledge_notes,
    list_studio_jobs,
    list_studio_sources,
    manual_add_url,
    process_source_jobs_once,
    studio_search,
    sync_readwise_for_studio,
)
from app.storage.repositories import SourceCatalogRepository
from app.storage.sqlite import Database

router = APIRouter(
    prefix="/studio",
    tags=["studio"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/sources", response_model=StudioSourceListResponse)
async def list_sources(
    q: str = Query("", description="Search title, URL, and description."),
    limit: int = Query(50, ge=1, le=500),
    metadata_only: bool = False,
    source_type: str = Query("", description="Filter by source type."),
    display_state: str = Query("", description="Filter by derived display state."),
    provider: str = Query("", description="Filter by provider."),
    tag: str = Query("", description="Filter by normalized tag."),
    db: Database = Depends(get_database),
):
    return StudioSourceListResponse(
        sources=list_studio_sources(
            db,
            query=q,
            limit=limit,
            metadata_only=metadata_only,
            source_type=source_type,
            display_state=display_state,
            provider=provider,
            tag=tag,
        )
    )


@router.get("/sources/{source_uid}", response_model=StudioSourceDetail)
async def source_detail(source_uid: str, db: Database = Depends(get_database)):
    detail = get_studio_source_detail(db, source_uid)
    if detail is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return detail


@router.get("/sources/{source_uid}/reader", response_model=StudioSourceReaderResponse)
async def source_reader(source_uid: str, db: Database = Depends(get_database)):
    settings = get_settings()
    reader = get_studio_source_reader(db, source_uid, vault_path=Path(settings.vault_path))
    if reader is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return reader


@router.post("/sources/manual", response_model=StudioManualAddResponse)
async def add_manual_source(req: StudioManualAddRequest, db: Database = Depends(get_database)):
    try:
        source, job = manual_add_url(
            db,
            url=req.url,
            title=req.title,
            tags=req.tags,
            enqueue_action=req.enqueue_action,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StudioManualAddResponse(
        source=source,
        job=StudioProcessingJobResponse.from_job(job) if job else None,
    )


@router.post(
    "/sources/{source_uid}/actions/enqueue",
    response_model=StudioProcessingJobResponse,
)
async def enqueue_action(
    source_uid: str,
    req: StudioEnqueueActionRequest,
    db: Database = Depends(get_database),
):
    try:
        job = enqueue_source_action(
            db,
            source_uid=source_uid,
            action=req.action,
            requested_by="studio",
            requested_reason=req.requested_reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    repo = SourceCatalogRepository(db)
    source = repo.get_source(job.source_uid)
    return StudioProcessingJobResponse.from_job(
        job,
        source_title=source.title if source else "",
        source_url=source.url if source else "",
        source_type=source.source_type if source else "",
        attempt_count=repo.processing_attempt_count(job.job_uid),
    )


@router.get("/jobs", response_model=StudioJobListResponse)
async def list_jobs(
    limit: int = Query(50, ge=1, le=500),
    status: str = "",
    db: Database = Depends(get_database),
):
    jobs = list_studio_jobs(db, limit=limit, status=status)
    return StudioJobListResponse(jobs=jobs)


@router.post("/jobs/process-once", response_model=StudioProcessJobsResponse)
async def process_jobs_once(
    limit: int = Query(5, ge=1, le=50),
    db: Database = Depends(get_database),
):
    jobs = await process_source_jobs_once(limit=limit)
    repo = SourceCatalogRepository(db)
    responses: list[StudioProcessingJobResponse] = []
    for job in jobs:
        source = repo.get_source(job.source_uid)
        responses.append(
            StudioProcessingJobResponse.from_job(
                job,
                source_title=source.title if source else "",
                source_url=source.url if source else "",
                source_type=source.source_type if source else "",
                attempt_count=repo.processing_attempt_count(job.job_uid),
            )
        )
    return StudioProcessJobsResponse(
        processed=len(responses),
        succeeded=sum(1 for job in responses if job.status == "completed"),
        failed=sum(1 for job in responses if job.status == "failed"),
        jobs=responses,
    )


@router.post("/readwise/sync", response_model=StudioReadwiseSyncResponse)
async def sync_readwise(req: StudioReadwiseSyncRequest):
    result = await sync_readwise_for_studio(
        limit=req.limit,
        force=req.force,
        auto_brief_limit=req.auto_brief_limit,
    )
    auto_brief = result.auto_brief_result
    return StudioReadwiseSyncResponse(
        imported_count=result.imported_count,
        failed_count=result.failed_count,
        auto_brief_compiled_count=auto_brief.compiled_count if auto_brief else 0,
        auto_brief_failed_count=auto_brief.failed_count if auto_brief else 0,
    )


@router.post("/briefs/pending", response_model=StudioBriefCompileResponse)
async def compile_pending_briefs(req: StudioPendingBriefRequest):
    result = await compile_pending_briefs_for_studio(limit=req.limit, force=req.force)
    return StudioBriefCompileResponse(
        compiled_count=result.compiled_count,
        failed_count=result.failed_count,
    )


@router.post("/sources/{source_uid}/brief", response_model=StudioBriefCompileResponse)
async def compile_source_brief_action(source_uid: str, req: StudioPendingBriefRequest):
    try:
        result = await compile_source_brief_for_studio(
            source_uid=source_uid,
            force=req.force,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return StudioBriefCompileResponse(
        compiled_count=result.compiled_count,
        failed_count=result.failed_count,
    )


@router.get("/search", response_model=StudioSearchResponse)
async def studio_search_endpoint(
    q: str = Query("", description="Combined search across catalog and read model."),
    limit: int = Query(25, ge=1, le=100),
    source_type: str = Query("", description="Filter source matches by type."),
    display_state: str = Query("", description="Filter source matches by display state."),
    db: Database = Depends(get_database),
):
    settings = get_settings()
    return studio_search(
        db,
        query=q,
        vault_path=Path(settings.vault_path),
        limit=limit,
        source_type=source_type,
        display_state=display_state,
    )


@router.get("/stats", response_model=StudioStatsResponse)
async def stats(db: Database = Depends(get_database)):
    settings = get_settings()
    return get_studio_stats(db, vault_path=Path(settings.vault_path))


@router.get("/knowledge/{note_type}", response_model=StudioKnowledgeListResponse)
async def knowledge_list(
    note_type: str,
    limit: int = Query(200, ge=1, le=2000),
):
    if note_type not in KNOWLEDGE_NOTE_TYPES:
        raise HTTPException(status_code=404, detail="Unsupported note type")
    settings = get_settings()
    return list_knowledge_notes(
        note_type=note_type,
        vault_path=Path(settings.vault_path),
        limit=limit,
    )


@router.get("/knowledge/note/detail", response_model=StudioKnowledgeDetailResponse)
async def knowledge_detail(
    note_path: str = Query(..., description="Vault-relative note path."),
):
    settings = get_settings()
    detail = get_knowledge_detail(
        note_path=note_path,
        vault_path=Path(settings.vault_path),
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return detail


@router.post("/snapshots/export", response_model=StudioSnapshotExportResponse)
async def export_snapshot(
    reason: str = "",
    db: Database = Depends(get_database),
):
    settings = get_settings()
    snapshot = SourceCatalogRepository(db).export_snapshot(
        default_snapshot_path(settings),
        reason=reason,
    )
    return StudioSnapshotExportResponse(**snapshot.model_dump())


@router.post("/snapshots/import", response_model=StudioSnapshotImportResponse)
async def import_snapshot(req: StudioSnapshotImportRequest, db: Database = Depends(get_database)):
    path = Path(req.snapshot_path).expanduser()
    if not path.exists():
        raise HTTPException(status_code=404, detail="Snapshot not found")
    imported = SourceCatalogRepository(db).import_snapshot(path)
    return StudioSnapshotImportResponse(imported=imported)
