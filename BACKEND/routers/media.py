from __future__ import annotations

import mimetypes

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from ..dependencies import current_session, storage_service
from ..services.auth import SessionContext
from ..services.storage import StorageService


router = APIRouter(prefix="/api/media", tags=["media"])


def _response(path):
    return FileResponse(
        path,
        media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        headers={
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/uploads/{upload_id}")
def upload_media(
    upload_id: str,
    ctx: SessionContext = Depends(current_session),
    storage: StorageService = Depends(storage_service),
):
    return _response(storage.owned_upload_path(upload_id, ctx.user["id"]))


@router.get("/tours/{tour_id}/{asset}")
def tour_media(
    tour_id: str,
    asset: str,
    ctx: SessionContext = Depends(current_session),
    storage: StorageService = Depends(storage_service),
):
    return _response(storage.owned_tour_asset(tour_id, asset, ctx.user["id"]))


@router.get("/profile/{user_id}")
def profile_media(
    user_id: str,
    ctx: SessionContext = Depends(current_session),
    storage: StorageService = Depends(storage_service),
):
    return _response(storage.profile_image_path(user_id, ctx.user["id"]))
