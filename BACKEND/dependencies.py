from __future__ import annotations

from fastapi import Request

from .config import Settings
from .database import Database
from .services.auth import AuthService, SessionContext
from .services.exports import ExportService
from .services.generation import GenerationService
from .services.sharing import SharingService
from .services.storage import StorageService


def settings(request: Request) -> Settings:
    return request.app.state.settings


def database(request: Request) -> Database:
    return request.app.state.database


def auth_service(request: Request) -> AuthService:
    return request.app.state.auth


def generation_service(request: Request) -> GenerationService:
    return request.app.state.generation


def storage_service(request: Request) -> StorageService:
    return request.app.state.storage


def export_service(request: Request) -> ExportService:
    return request.app.state.exports


def sharing_service(request: Request) -> SharingService:
    return request.app.state.sharing


def current_session(request: Request) -> SessionContext:
    return auth_service(request).authenticate(request)
