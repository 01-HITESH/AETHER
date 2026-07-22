from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .database import Database, utc_now
from .routers import auth, jobs, media, tours, uploads, users
from .services.auth import AuthService
from .services.exports import ExportService
from .services.generation import GenerationService
from .services.security import Limit, RateLimiter
from .services.sharing import SharingService
from .services.storage import StorageService


def create_app(config: Settings | None = None) -> FastAPI:
    settings = config or Settings.from_env()
    database = Database(settings)
    auth_service = AuthService(settings, database)
    storage_service = StorageService(settings, database)
    generation_service = GenerationService(settings, database)
    sharing_service = SharingService(settings, database)
    export_service = ExportService(settings)
    limiter = RateLimiter(settings.rate_limit_enabled)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        database.initialize()
        generation_service.start()
        try:
            yield
        finally:
            generation_service.stop()

    app = FastAPI(
        title="AETHER API",
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings
    app.state.database = database
    app.state.auth = auth_service
    app.state.storage = storage_service
    app.state.generation = generation_service
    app.state.sharing = sharing_service
    app.state.exports = export_service
    app.state.rate_limiter = limiter

    @app.middleware("http")
    async def security_and_rate_limits(request: Request, call_next):
        origin = request.headers.get("origin", "")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
            parsed = urlparse(origin)
            if parsed.netloc and parsed.netloc != request.headers.get("host", ""):
                return JSONResponse({"detail": "Cross-origin request blocked."}, status_code=403)

        limit = _limit_for(request)
        if limit:
            client = request.client.host if request.client else "unknown"
            retry_after = limiter.check(f"{client}:{limit[0]}", limit[1])
            if retry_after:
                return JSONResponse(
                    {"detail": "Too many requests. Try again later."},
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )

        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'",
        )
        return response

    @app.get("/api/health", tags=["system"])
    def health() -> dict:
        return {
            "ok": True,
            "name": "AETHER API",
            "version": "2.0.0",
            "time": utc_now(),
        }

    @app.get("/api/config", tags=["system"])
    def frontend_config() -> dict:
        selected = generation_service.resolve_provider(settings.generation_provider)
        return {
            "google_client_id": settings.google_client_ids[0] if settings.google_client_ids else "",
            "google_auth_enabled": bool(settings.google_client_ids),
            "generation": {
                "active_provider": selected,
                "default_model": settings.generation_model,
                "default_variants": settings.generation_variants,
                "providers": [
                    {
                        "id": "local_demo",
                        "name": "Local demo renderer",
                        "configured": True,
                        "real_inference": False,
                    },
                    {
                        "id": "comfyui",
                        "name": "ComfyUI",
                        "configured": bool(settings.comfyui_workflow_path),
                        "real_inference": True,
                    },
                    {
                        "id": "cloud",
                        "name": "Cloud provider",
                        "configured": bool(settings.cloud_generation_url),
                        "real_inference": True,
                    },
                ],
            },
        }

    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(uploads.router)
    app.include_router(uploads.legacy_router)
    app.include_router(jobs.router)
    app.include_router(jobs.legacy_router)
    app.include_router(tours.router)
    app.include_router(tours.share_router)
    app.include_router(media.router)

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/app/")

    frontend_root = _frontend_root(settings)
    if frontend_root.exists():
        app.mount("/app", StaticFiles(directory=frontend_root, html=True), name="frontend")

    return app


def _frontend_root(settings: Settings) -> Path:
    if (settings.frontend_dist_dir / "index.html").is_file():
        return settings.frontend_dist_dir
    return settings.frontend_dir


def _limit_for(request: Request) -> tuple[str, Limit] | None:
    path = request.url.path
    if request.method == "POST" and path in {
        "/api/auth/register",
        "/api/auth/login",
        "/api/auth/google",
        "/api/auth/password-reset/request",
        "/api/auth/password-reset/confirm",
    }:
        return "authentication", Limit(12, 60)
    if request.method == "POST" and path in {"/api/upload", "/api/uploads", "/api/uploads/"}:
        return "upload", Limit(30, 3600)
    if request.method == "POST" and (
        path == "/api/generation/jobs" or path == "/api/tours" or path.endswith("/retry")
    ):
        return "generation", Limit(20, 3600)
    return None


app = create_app()
