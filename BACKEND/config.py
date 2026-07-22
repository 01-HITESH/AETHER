from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, replace
from pathlib import Path


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
    legacy_db_path: Path
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
    google_client_ids: tuple[str, ...]
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_from: str
    smtp_use_tls: bool
    rate_limit_enabled: bool

    @classmethod
    def from_env(cls, root: Path | None = None) -> "Settings":
        project_root = (root or Path(__file__).resolve().parents[1]).resolve()
        data_dir = Path(os.getenv("AETHER_DATA_DIR", project_root / "BACKEND" / "data")).resolve()
        database_dir = data_dir / "database"
        data_dir.mkdir(parents=True, exist_ok=True)
        secret_key = os.getenv("AETHER_SECRET_KEY", "").strip() or _load_or_create_secret(data_dir)
        google_ids = tuple(
            value.strip()
            for value in os.getenv("GOOGLE_CLIENT_IDS", os.getenv("GOOGLE_CLIENT_ID", "")).split(",")
            if value.strip()
        )
        return cls(
            root=project_root,
            frontend_dir=project_root / "FRONTEND",
            frontend_dist_dir=project_root / "FRONTEND" / "dist",
            data_dir=data_dir,
            database_dir=database_dir,
            uploads_dir=data_dir / "uploads",
            profile_images_dir=data_dir / "profile_images",
            tours_dir=data_dir / "tours",
            exports_dir=data_dir / "exports",
            db_path=Path(os.getenv("AETHER_DB_PATH", database_dir / "aether.sqlite3")).resolve(),
            legacy_db_path=data_dir / "aether.sqlite3",
            environment=os.getenv("AETHER_ENV", "development").strip().lower(),
            secret_key=secret_key,
            cookie_name=os.getenv("AETHER_SESSION_COOKIE", "aether_session"),
            cookie_secure=_env_bool("AETHER_COOKIE_SECURE", False),
            session_ttl_seconds=max(300, int(os.getenv("AETHER_SESSION_TTL_SECONDS", str(7 * 24 * 60 * 60)))),
            password_reset_ttl_seconds=max(300, int(os.getenv("AETHER_PASSWORD_RESET_TTL_SECONDS", "1800"))),
            max_upload_bytes=max(1, int(os.getenv("AETHER_MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))),
            max_profile_image_bytes=max(
                1, int(os.getenv("AETHER_MAX_PROFILE_IMAGE_BYTES", str(25 * 1024 * 1024)))
            ),
            generation_provider=os.getenv("AETHER_GENERATION_PROVIDER", "auto").strip().lower(),
            generation_model=os.getenv("AETHER_GENERATION_MODEL", "local-demo-v2").strip(),
            generation_variants=min(4, max(3, int(os.getenv("AETHER_GENERATION_VARIANTS", "4")))),
            comfyui_url=os.getenv("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/"),
            comfyui_workflow_path=os.getenv("COMFYUI_WORKFLOW_PATH", "").strip(),
            cloud_generation_url=os.getenv("AETHER_CLOUD_GENERATION_URL", "").strip(),
            cloud_generation_api_key=os.getenv("AETHER_CLOUD_GENERATION_API_KEY", "").strip(),
            google_client_ids=google_ids,
            smtp_host=os.getenv("AETHER_SMTP_HOST", "").strip(),
            smtp_port=int(os.getenv("AETHER_SMTP_PORT", "587")),
            smtp_username=os.getenv("AETHER_SMTP_USERNAME", "").strip(),
            smtp_password=os.getenv("AETHER_SMTP_PASSWORD", ""),
            smtp_from=os.getenv("AETHER_SMTP_FROM", "AETHER <no-reply@localhost>").strip(),
            smtp_use_tls=_env_bool("AETHER_SMTP_USE_TLS", True),
            rate_limit_enabled=_env_bool("AETHER_RATE_LIMIT_ENABLED", True),
        )

    def ensure_directories(self) -> None:
        for path in (
            self.data_dir,
            self.database_dir,
            self.uploads_dir,
            self.profile_images_dir,
            self.tours_dir,
            self.exports_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def with_data_dir(self, data_dir: Path, **changes: object) -> "Settings":
        resolved = data_dir.resolve()
        database_dir = resolved / "database"
        return replace(
            self,
            data_dir=resolved,
            database_dir=database_dir,
            uploads_dir=resolved / "uploads",
            profile_images_dir=resolved / "profile_images",
            tours_dir=resolved / "tours",
            exports_dir=resolved / "exports",
            db_path=database_dir / "aether.sqlite3",
            legacy_db_path=resolved / "aether.sqlite3",
            **changes,
        )


def _load_or_create_secret(data_dir: Path) -> str:
    path = data_dir / ".secret_key"
    if path.exists():
        value = path.read_text(encoding="ascii").strip()
        if value:
            return value
    value = secrets.token_urlsafe(48)
    path.write_text(value, encoding="ascii")
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
