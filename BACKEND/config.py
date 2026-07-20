from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    root: Path
    frontend_dir: Path
    frontend_dist_dir: Path
    data_dir: Path
    database_dir: Path
    uploads_dir: Path
    profile_images_dir: Path
    tours_dir: Path
    exports_dir: Path
    db_path: Path
    environment: str
    secret_key: str
    cookie_name: str
    cookie_secure: bool
    session_ttl_seconds: int
    password_reset_ttl_seconds: int
    max_upload_bytes: int
    max_profile_image_bytes: int
    generation_provider: str
    generation_model: str
    generation_variants: int
    comfyui_url: str
    comfyui_workflow_path: str
    cloud_generation_url: str
    cloud_generation_api_key: str
    rate_limit_enabled: bool


def load_settings() -> Settings:
    root = Path(__file__).resolve().parents[1]
    data = Path(os.getenv("AETHER_DATA_DIR", str(root / "BACKEND" / "data"))).resolve()
    frontend = root / "FRONTEND"
    return Settings(
        root=root,
        frontend_dir=frontend,
        frontend_dist_dir=frontend / "dist",
        data_dir=data,
        database_dir=data / "database",
        uploads_dir=data / "uploads",
        profile_images_dir=data / "profile_images",
        tours_dir=data / "tours",
        exports_dir=data / "exports",
        db_path=Path(os.getenv("AETHER_DB_PATH", str(data / "database" / "aether.sqlite3"))).resolve(),
        environment=os.getenv("AETHER_ENV", "development"),
        secret_key=os.getenv("AETHER_SECRET_KEY", "development-only-change-me"),
        cookie_name=os.getenv("AETHER_COOKIE_NAME", "aether_session"),
        cookie_secure=_bool("AETHER_COOKIE_SECURE", False),
        session_ttl_seconds=int(os.getenv("AETHER_SESSION_TTL", "604800")),
        password_reset_ttl_seconds=int(os.getenv("AETHER_RESET_TTL", "1800")),
        max_upload_bytes=int(os.getenv("AETHER_MAX_UPLOAD_BYTES", str(20 * 1024 * 1024))),
        max_profile_image_bytes=int(os.getenv("AETHER_MAX_PROFILE_BYTES", str(25 * 1024 * 1024))),
        generation_provider=os.getenv("AETHER_GENERATION_PROVIDER", "local_demo").lower(),
        generation_model=os.getenv("AETHER_GENERATION_MODEL", "aether-local-v2"),
        generation_variants=max(1, min(4, int(os.getenv("AETHER_GENERATION_VARIANTS", "4")))),
        comfyui_url=os.getenv("AETHER_COMFYUI_URL", "http://127.0.0.1:8188"),
        comfyui_workflow_path=os.getenv("AETHER_COMFYUI_WORKFLOW", ""),
        cloud_generation_url=os.getenv("AETHER_CLOUD_GENERATION_URL", ""),
        cloud_generation_api_key=os.getenv("AETHER_CLOUD_GENERATION_API_KEY", ""),
        rate_limit_enabled=_bool("AETHER_RATE_LIMIT_ENABLED", True),
    )

