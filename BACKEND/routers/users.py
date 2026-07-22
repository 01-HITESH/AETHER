from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile

from ..config import Settings
from ..database import Database
from ..dependencies import auth_service, current_session, database, settings, storage_service
from ..models.schemas import PasswordPatch, ProfilePatch, TwoFactorVerifyPayload
from ..repositories.users import UsersRepository
from ..services.auth import AuthService, SessionContext
from ..services.storage import StorageService


router = APIRouter(prefix="/api/me", tags=["account"])


@router.get("")
def me(
    ctx: SessionContext = Depends(current_session),
    auth: AuthService = Depends(auth_service),
    db: Database = Depends(database),
) -> dict:
    stats, history = UsersRepository(db).stats_and_history(ctx.user["id"])
    return {
        "user": auth.user_to_dict(ctx.user),
        "stats": {
            "projects": int(stats["projects"] or 0),
            "saved": int(stats["saved"] or 0),
            "favorites": int(stats["favorites"] or 0),
        },
        "history": [auth.history_to_dict(row) for row in history],
    }


@router.patch("")
def patch_me(
    payload: ProfilePatch,
    ctx: SessionContext = Depends(current_session),
    auth: AuthService = Depends(auth_service),
    db: Database = Depends(database),
) -> dict:
    submitted_name = payload.username if payload.username is not None else payload.name
    name = (submitted_name if submitted_name is not None else ctx.user["name"]).strip()
    if not name:
        raise HTTPException(status_code=400, detail="Profile name cannot be empty.")
    current_settings = json.loads(ctx.user["settings_json"] or "{}")
    if payload.settings:
        current_settings.update(payload.settings)
    updated = UsersRepository(db).update_profile(ctx.user["id"], name, current_settings)
    return {"user": auth.user_to_dict(updated)}


@router.patch("/password")
def change_password(
    payload: PasswordPatch,
    response: Response,
    ctx: SessionContext = Depends(current_session),
    auth: AuthService = Depends(auth_service),
    config: Settings = Depends(settings),
) -> dict:
    if not auth.passwords.verify(
        payload.currentPassword, ctx.user["password_hash"], ctx.user["salt"]
    ):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")
    auth.validate_password(payload.newPassword)
    auth.users.update_password(ctx.user["id"], auth.passwords.hash(payload.newPassword))
    auth.revoke_all_sessions(ctx.user["id"])
    response.delete_cookie(config.cookie_name, path="/", samesite="strict")
    return {"ok": True, "reauthenticate": True}


@router.post("/profile-image")
async def profile_image(
    file: UploadFile = File(...),
    ctx: SessionContext = Depends(current_session),
    auth: AuthService = Depends(auth_service),
    storage: StorageService = Depends(storage_service),
) -> dict:
    user = await storage.store_profile_image(file, ctx.user)
    return {"user": auth.user_to_dict(user)}


@router.get("/sessions")
def sessions(
    ctx: SessionContext = Depends(current_session),
    auth: AuthService = Depends(auth_service),
) -> dict:
    return {"sessions": auth.list_sessions(ctx.user["id"], ctx.token_hash)}


@router.delete("/sessions/{session_id}")
def revoke_session(
    session_id: str,
    ctx: SessionContext = Depends(current_session),
    auth: AuthService = Depends(auth_service),
) -> dict[str, bool]:
    if not auth.revoke_named_session(ctx.user["id"], session_id, ctx.token_hash):
        raise HTTPException(status_code=404, detail="Session was not found.")
    return {"ok": True}


@router.post("/two-factor/setup")
def setup_two_factor(
    ctx: SessionContext = Depends(current_session),
    auth: AuthService = Depends(auth_service),
) -> dict:
    return auth.totp_setup(ctx.user)


@router.post("/two-factor/enable")
def enable_two_factor(
    payload: TwoFactorVerifyPayload,
    ctx: SessionContext = Depends(current_session),
    auth: AuthService = Depends(auth_service),
) -> dict:
    user = auth.enable_totp(ctx.user["id"], payload.code)
    return {"user": auth.user_to_dict(user)}


@router.post("/two-factor/disable")
def disable_two_factor(
    payload: TwoFactorVerifyPayload,
    ctx: SessionContext = Depends(current_session),
    auth: AuthService = Depends(auth_service),
) -> dict:
    user = auth.disable_totp(ctx.user["id"], payload.code)
    return {"user": auth.user_to_dict(user)}
