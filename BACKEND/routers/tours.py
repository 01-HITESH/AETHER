from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse

from ..config import Settings
from ..dependencies import (
    current_session,
    export_service,
    settings,
    sharing_service,
)
from ..models.schemas import ShareCreatePayload, ShareUnlockPayload
from ..repositories.tours import ToursRepository, tour_to_dict
from ..services.auth import SessionContext
from ..services.exports import ExportService, safe_filename
from ..services.sharing import SharingService


router = APIRouter(prefix="/api/tours", tags=["designs"])


@router.get("")
def list_tours(
    ctx: SessionContext = Depends(current_session),
    config: Settings = Depends(settings),
) -> dict:
    repository = ToursRepository(ctx_database(ctx), config)
    return {"tours": [tour_to_dict(row) for row in repository.list_for_user(ctx.user["id"])]}


@router.get("/{tour_id}")
def get_tour(
    tour_id: str,
    ctx: SessionContext = Depends(current_session),
    config: Settings = Depends(settings),
) -> dict:
    row = ToursRepository(ctx_database(ctx), config).require(tour_id, ctx.user["id"])
    return {"tour": tour_to_dict(row)}


@router.post("/{tour_id}/save")
def save_tour(
    tour_id: str,
    ctx: SessionContext = Depends(current_session),
    config: Settings = Depends(settings),
) -> dict:
    row = ToursRepository(ctx_database(ctx), config).toggle(tour_id, ctx.user["id"], "saved")
    return {"tour": tour_to_dict(row)}


@router.post("/{tour_id}/favorite")
def favorite_tour(
    tour_id: str,
    ctx: SessionContext = Depends(current_session),
    config: Settings = Depends(settings),
) -> dict:
    row = ToursRepository(ctx_database(ctx), config).toggle(tour_id, ctx.user["id"], "favorite")
    return {"tour": tour_to_dict(row)}


@router.delete("/{tour_id}")
def delete_tour(
    tour_id: str,
    ctx: SessionContext = Depends(current_session),
    config: Settings = Depends(settings),
) -> dict[str, bool]:
    ToursRepository(ctx_database(ctx), config).delete(tour_id, ctx.user["id"])
    return {"ok": True}


@router.get("/{tour_id}/export/{kind}")
def export_tour(
    tour_id: str,
    kind: str,
    ctx: SessionContext = Depends(current_session),
    config: Settings = Depends(settings),
    exports: ExportService = Depends(export_service),
) -> FileResponse:
    tour = ToursRepository(ctx_database(ctx), config).require(tour_id, ctx.user["id"])
    name = safe_filename(tour["title"])
    if kind in {"hd", "image", "redesign", "render"}:
        return FileResponse(
            Path(tour["redesign_path"]),
            filename=f"{name}-redesign.jpg",
            media_type="image/jpeg",
        )
    if kind in {"pano", "panorama"}:
        return FileResponse(
            Path(tour["pano_path"]),
            filename=f"{name}-panorama.jpg",
            media_type="image/jpeg",
        )
    if kind in {"report", "html"}:
        return FileResponse(
            exports.report(tour), filename=f"{name}-report.html", media_type="text/html"
        )
    if kind in {"model", "obj"}:
        return FileResponse(
            exports.obj_package(tour),
            filename=f"{name}-obj.zip",
            media_type="application/zip",
        )
    raise HTTPException(status_code=404, detail="Unsupported export type.")


@router.post("/{tour_id}/shares", status_code=201)
def create_share(
    tour_id: str,
    payload: ShareCreatePayload,
    ctx: SessionContext = Depends(current_session),
    sharing: SharingService = Depends(sharing_service),
) -> dict:
    return {"share": sharing.create(tour_id, ctx.user["id"], payload.expiresHours, payload.password)}


share_router = APIRouter(prefix="/api/shares", tags=["sharing"])


@share_router.post("/{token}")
def open_share(
    token: str,
    payload: ShareUnlockPayload,
    sharing: SharingService = Depends(sharing_service),
) -> dict:
    return sharing.shared_tour(token, payload.password)


@share_router.get("/{token}")
def open_unprotected_share(
    token: str,
    sharing: SharingService = Depends(sharing_service),
) -> dict:
    return sharing.shared_tour(token, "")


@share_router.get("/{token}/media/{asset}")
def shared_media(
    token: str,
    asset: str,
    x_share_password: str = Header(default="", alias="X-Share-Password"),
    sharing: SharingService = Depends(sharing_service),
) -> FileResponse:
    target = sharing.shared_asset(token, asset, x_share_password)
    return FileResponse(
        target,
        media_type=mimetypes.guess_type(target.name)[0] or "application/octet-stream",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


def ctx_database(ctx: SessionContext):
    return ctx.database
