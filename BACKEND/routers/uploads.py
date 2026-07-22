from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile

from ..dependencies import current_session, storage_service
from ..services.auth import SessionContext
from ..services.storage import StorageService


router = APIRouter(prefix="/api/uploads", tags=["uploads"])


@router.post("", status_code=201)
@router.post("/", status_code=201, include_in_schema=False)
async def upload_room(
    file: UploadFile = File(...),
    ctx: SessionContext = Depends(current_session),
    storage: StorageService = Depends(storage_service),
) -> dict:
    return await storage.store_upload(file, ctx.user["id"])


legacy_router = APIRouter(prefix="/api", tags=["uploads"])


@legacy_router.post("/upload", status_code=201, include_in_schema=False)
async def legacy_upload_room(
    file: UploadFile = File(...),
    ctx: SessionContext = Depends(current_session),
    storage: StorageService = Depends(storage_service),
) -> dict:
    return await storage.store_upload(file, ctx.user["id"])
