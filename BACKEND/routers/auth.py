from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from ..config import Settings
from ..dependencies import auth_service, current_session, settings
from ..models.schemas import (
    GoogleAuthPayload,
    LoginPayload,
    PasswordResetConfirmPayload,
    PasswordResetRequestPayload,
    RegisterPayload,
)
from ..services.auth import AuthService, SessionContext


router = APIRouter(prefix="/api/auth", tags=["authentication"])


def _set_cookie(response: Response, raw_token: str, config: Settings) -> None:
    response.set_cookie(
        config.cookie_name,
        raw_token,
        max_age=config.session_ttl_seconds,
        httponly=True,
        secure=config.cookie_secure,
        samesite="strict",
        path="/",
    )


@router.post("/register", status_code=201)
def register(
    payload: RegisterPayload,
    request: Request,
    response: Response,
    auth: AuthService = Depends(auth_service),
    config: Settings = Depends(settings),
) -> dict:
    user = auth.register(payload.name, payload.email, payload.password)
    raw = auth.create_session(user["id"], request)
    _set_cookie(response, raw, config)
    return {"user": auth.user_to_dict(user)}


@router.post("/login")
def login(
    payload: LoginPayload,
    request: Request,
    response: Response,
    auth: AuthService = Depends(auth_service),
    config: Settings = Depends(settings),
) -> dict:
    user = auth.login(payload.email, payload.password, payload.otp)
    raw = auth.create_session(user["id"], request)
    _set_cookie(response, raw, config)
    return {"user": auth.user_to_dict(user)}


@router.post("/google")
def google_login(
    payload: GoogleAuthPayload,
    request: Request,
    response: Response,
    auth: AuthService = Depends(auth_service),
    config: Settings = Depends(settings),
) -> dict:
    user = auth.google_login(payload.credential)
    raw = auth.create_session(user["id"], request)
    _set_cookie(response, raw, config)
    return {"user": auth.user_to_dict(user)}


@router.post("/logout")
def logout(
    response: Response,
    ctx: SessionContext = Depends(current_session),
    auth: AuthService = Depends(auth_service),
    config: Settings = Depends(settings),
) -> dict[str, bool]:
    auth.revoke_session(ctx.token_hash, ctx.user["id"])
    response.delete_cookie(config.cookie_name, path="/", samesite="strict")
    return {"ok": True}


@router.post("/password-reset/request")
def request_password_reset(
    payload: PasswordResetRequestPayload,
    auth: AuthService = Depends(auth_service),
) -> dict:
    development_token, message = auth.create_password_reset(payload.email)
    result = {"ok": True, "message": message}
    if development_token:
        result["development_reset_token"] = development_token
    return result


@router.post("/password-reset/confirm")
def confirm_password_reset(
    payload: PasswordResetConfirmPayload,
    response: Response,
    auth: AuthService = Depends(auth_service),
    config: Settings = Depends(settings),
) -> dict[str, bool]:
    auth.confirm_password_reset(payload.token, payload.newPassword)
    response.delete_cookie(config.cookie_name, path="/", samesite="strict")
    return {"ok": True}
