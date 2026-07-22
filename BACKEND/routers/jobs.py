from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import current_session, generation_service
from ..models.schemas import GenerationJobCreatePayload
from ..repositories.jobs import JobsRepository
from ..services.auth import SessionContext
from ..services.generation import GenerationService


router = APIRouter(prefix="/api/generation/jobs", tags=["generation"])


@router.post("", status_code=202)
def create_job(
    payload: GenerationJobCreatePayload,
    ctx: SessionContext = Depends(current_session),
    generation: GenerationService = Depends(generation_service),
) -> dict:
    try:
        return {"job": generation.create_job(ctx.user["id"], payload)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def list_jobs(
    ctx: SessionContext = Depends(current_session),
    generation: GenerationService = Depends(generation_service),
) -> dict:
    rows = generation.jobs.list_for_user(ctx.user["id"])
    return {"jobs": [generation.job_to_dict(row) for row in rows]}


@router.get("/{job_id}")
def get_job(
    job_id: str,
    ctx: SessionContext = Depends(current_session),
    generation: GenerationService = Depends(generation_service),
) -> dict:
    row = generation.jobs.get(job_id, ctx.user["id"])
    if not row:
        raise HTTPException(status_code=404, detail="Generation job was not found.")
    return {"job": generation.job_to_dict(row)}


@router.post("/{job_id}/cancel")
def cancel_job(
    job_id: str,
    ctx: SessionContext = Depends(current_session),
    generation: GenerationService = Depends(generation_service),
) -> dict:
    row = generation.jobs.cancel(job_id, ctx.user["id"])
    if not row:
        raise HTTPException(status_code=404, detail="Generation job was not found.")
    generation.notify()
    return {"job": generation.job_to_dict(row)}


@router.post("/{job_id}/retry", status_code=202)
def retry_job(
    job_id: str,
    ctx: SessionContext = Depends(current_session),
    generation: GenerationService = Depends(generation_service),
) -> dict:
    row = generation.jobs.retry(job_id, ctx.user["id"])
    if not row:
        raise HTTPException(status_code=409, detail="Only failed or cancelled jobs can be retried.")
    generation.notify()
    return {"job": generation.job_to_dict(row)}


legacy_router = APIRouter(prefix="/api", tags=["generation"])


@legacy_router.post("/tours", status_code=202, include_in_schema=False)
def legacy_create_job(
    payload: GenerationJobCreatePayload,
    ctx: SessionContext = Depends(current_session),
    generation: GenerationService = Depends(generation_service),
) -> dict:
    job = generation.create_job(ctx.user["id"], payload)
    return {"jobId": job["id"], "job": job}
