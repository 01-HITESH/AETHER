from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps

from ..config import Settings
from ..database import Database, path_is_within, utc_now
from ..repositories.users import UsersRepository
from .security import new_id


ALLOWED_ROOM_TYPES = {"image/jpeg", "image/png", "image/jpg"}
ALLOWED_PROFILE_TYPES = {"image/jpeg", "image/png", "image/jpg", "image/webp"}


class StorageService:
    def __init__(self, settings: Settings, database: Database):
        self.settings = settings
        self.database = database

    async def store_upload(self, file: UploadFile, user_id: str) -> dict[str, Any]:
        content_type = (file.content_type or "").lower()
        if content_type not in ALLOWED_ROOM_TYPES:
            raise HTTPException(status_code=400, detail="Please upload a JPG or PNG image.")
        data = await file.read(self.settings.max_upload_bytes + 1)
        if len(data) > self.settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail="Image exceeds the 20 MB limit.")
        image = self._read_image(data, profile=False)
        upload_id = new_id("upl")
        target_dir = self.settings.uploads_dir / upload_id
        target_dir.mkdir(parents=True, exist_ok=True)
        ext = ".jpg" if content_type in {"image/jpeg", "image/jpg"} else ".png"
        target = target_dir / f"source{ext}"
        if ext == ".jpg":
            image.save(target, "JPEG", quality=92, optimize=True)
        else:
            image.save(target, "PNG", optimize=True)
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO uploads (id, user_id, filename, content_type, path, width, height, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    upload_id,
                    user_id,
                    file.filename or f"upload{ext}",
                    content_type,
                    str(target),
                    image.width,
                    image.height,
                    utc_now(),
                ),
            )
            UsersRepository.log_history(
                conn,
                user_id,
                "room_uploaded",
                "Uploaded a room photo.",
                {
                    "upload_id": upload_id,
                    "filename": file.filename or f"upload{ext}",
                    "width": image.width,
                    "height": image.height,
                },
            )
        return {
            "uploadId": upload_id,
            "filename": file.filename or target.name,
            "width": image.width,
            "height": image.height,
            "url": f"/api/media/uploads/{upload_id}",
        }

    async def store_profile_image(self, file: UploadFile, user: Any) -> Any:
        content_type = (file.content_type or "").lower()
        if content_type not in ALLOWED_PROFILE_TYPES:
            raise HTTPException(status_code=400, detail="Please upload a JPG, PNG, or WebP image.")
        data = await file.read(self.settings.max_profile_image_bytes + 1)
        if len(data) > self.settings.max_profile_image_bytes:
            raise HTTPException(status_code=413, detail="Profile image exceeds the 25 MB limit.")
        image = self._read_image(data, profile=True)
        ext = { "image/png": ".png", "image/webp": ".webp" }.get(content_type, ".jpg")
        target_dir = self.settings.profile_images_dir / user["id"]
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"avatar{ext}"
        old_path = Path(user["profile_image_path"]) if user["profile_image_path"] else None
        if old_path and old_path != target and old_path.exists() and path_is_within(old_path, self.settings.profile_images_dir):
            old_path.unlink()
        if ext == ".png":
            image.save(target, "PNG", optimize=True)
        elif ext == ".webp":
            image.save(target, "WEBP", quality=90, method=6)
        else:
            image.convert("RGB").save(target, "JPEG", quality=92, optimize=True)
        return UsersRepository(self.database).set_profile_image(
            user["id"],
            path=str(target),
            content_type=content_type,
            width=image.width,
            height=image.height,
            filename=file.filename or target.name,
            byte_count=len(data),
        )

    def require_upload(self, upload_id: str, user_id: str) -> Any:
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT * FROM uploads WHERE id = ? AND user_id = ?", (upload_id, user_id)
            ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Uploaded room photo was not found.")
        return row

    def owned_upload_path(self, upload_id: str, user_id: str) -> Path:
        row = self.require_upload(upload_id, user_id)
        return self._safe_file(Path(row["path"]), self.settings.uploads_dir)

    def owned_tour_asset(self, tour_id: str, asset: str, user_id: str) -> Path:
        columns = {
            "redesign": "redesign_path",
            "panorama": "pano_path",
            "thumbnail": "thumb_path",
        }
        if asset not in columns:
            raise HTTPException(status_code=404, detail="Media not found.")
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT * FROM tours WHERE id = ? AND user_id = ?", (tour_id, user_id)
            ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Media not found.")
        return self._safe_file(Path(row[columns[asset]]), self.settings.tours_dir)

    def profile_image_path(self, requested_user_id: str, current_user_id: str) -> Path:
        if requested_user_id != current_user_id:
            raise HTTPException(status_code=404, detail="Media not found.")
        with self.database.connect() as conn:
            row = conn.execute("SELECT profile_image_path FROM users WHERE id = ?", (requested_user_id,)).fetchone()
        if not row or not row["profile_image_path"]:
            raise HTTPException(status_code=404, detail="Profile image not found.")
        return self._safe_file(Path(row["profile_image_path"]), self.settings.profile_images_dir)

    @staticmethod
    def _read_image(data: bytes, profile: bool) -> Image.Image:
        try:
            probe = Image.open(io.BytesIO(data))
            probe.verify()
            image = Image.open(io.BytesIO(data))
            image = ImageOps.exif_transpose(image)
            return image.convert("RGBA" if profile and image.mode == "RGBA" else "RGB")
        except Exception as exc:
            raise HTTPException(status_code=400, detail="The uploaded file is not a readable image.") from exc

    @staticmethod
    def _safe_file(path: Path, root: Path) -> Path:
        if not path.is_file() or not path_is_within(path, root):
            raise HTTPException(status_code=404, detail="Media not found.")
        return path
