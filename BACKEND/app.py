from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import mimetypes
import os
import secrets
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps
from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "FRONTEND"
DATA_DIR = ROOT / "BACKEND" / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
TOURS_DIR = DATA_DIR / "tours"
EXPORTS_DIR = DATA_DIR / "exports"
DB_PATH = DATA_DIR / "aether.sqlite3"

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/jpg"}

ROOM_LABELS = {
    "living_room": "Living Room",
    "bedroom": "Bedroom",
    "kitchen": "Kitchen",
    "bathroom": "Bathroom",
    "office": "Office",
    "hall": "Hall",
}

STYLE_LABELS = {
    "modern": "Modern",
    "minimalist": "Minimalist",
    "luxury": "Luxury",
    "scandinavian": "Scandinavian",
    "japanese_zen": "Japanese Zen",
    "industrial": "Industrial",
    "contemporary": "Contemporary",
    "traditional": "Traditional",
    "bohemian": "Bohemian",
    "classical": "Classical",
}

STYLE_TINTS = {
    "modern": (1.02, 1.01, 0.98),
    "minimalist": (1.06, 1.05, 1.03),
    "luxury": (1.08, 1.02, 0.91),
    "scandinavian": (1.07, 1.06, 1.01),
    "japanese_zen": (0.98, 1.04, 0.96),
    "industrial": (0.92, 0.94, 0.98),
    "contemporary": (1.03, 1.02, 1.0),
    "traditional": (1.03, 0.98, 0.92),
    "bohemian": (1.07, 0.98, 0.9),
    "classical": (1.05, 1.01, 0.96),
}


class LoginPayload(BaseModel):
    email: str
    password: str


class RegisterPayload(LoginPayload):
    name: str = Field(default="Designer")


class ProfilePatch(BaseModel):
    name: str | None = None
    settings: dict[str, Any] | None = None


class TourCreatePayload(BaseModel):
    uploadId: str
    roomType: str = "living_room"
    style: str = "modern"
    requirements: dict[str, Any] = Field(default_factory=dict)


app = FastAPI(title="AETHER Local API", version="1.0.0")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dirs() -> None:
    for path in (DATA_DIR, UPLOADS_DIR, TOURS_DIR, EXPORTS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def db() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    ensure_dirs()
    with db() as conn:
        conn.executescript(
            """
            PRAGMA journal_mode = WAL;

            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                settings_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS uploads (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                content_type TEXT NOT NULL,
                path TEXT NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS tours (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                upload_id TEXT NOT NULL,
                title TEXT NOT NULL,
                room_type TEXT NOT NULL,
                style TEXT NOT NULL,
                requirements_json TEXT NOT NULL DEFAULT '{}',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                pano_path TEXT NOT NULL,
                thumb_path TEXT NOT NULL,
                source_path TEXT NOT NULL,
                saved INTEGER NOT NULL DEFAULT 0,
                favorite INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(upload_id) REFERENCES uploads(id) ON DELETE CASCADE
            );
            """
        )


@app.on_event("startup")
def on_startup() -> None:
    init_db()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 180_000)
    return base64.b64encode(digest).decode("ascii")


def verify_password(password: str, salt: str, expected: str) -> bool:
    return hmac.compare_digest(hash_password(password, salt), expected)


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(12).replace('-', '').replace('_', '')}"


def public_path(path: Path) -> str:
    rel = path.resolve().relative_to(DATA_DIR.resolve()).as_posix()
    return f"/media/{rel}"


def row_to_user(row: sqlite3.Row) -> dict[str, Any]:
    settings = json.loads(row["settings_json"] or "{}")
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "settings": settings,
        "created_at": row["created_at"],
    }


def create_session(user_id: str) -> str:
    raw = secrets.token_urlsafe(32)
    with db() as conn:
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at) VALUES (?, ?, ?)",
            (token_hash(raw), user_id, utc_now()),
        )
    return raw


def bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization token.")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid authorization header.")
    return token


def current_user(authorization: str | None = Header(default=None)) -> sqlite3.Row:
    token = bearer_token(authorization)
    return user_from_token(token)


def user_from_token(token: str) -> sqlite3.Row:
    with db() as conn:
        row = conn.execute(
            """
            SELECT users.*
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ?
            """,
            (token_hash(token),),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")
    return row


def validate_email(email: str) -> str:
    value = email.strip().lower()
    if "@" not in value or "." not in value.rsplit("@", 1)[-1]:
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    return value


def safe_json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=True, separators=(",", ":"))


def image_response_headers() -> dict[str, str]:
    return {"Cache-Control": "public, max-age=3600"}


def apply_style_tint(image: Image.Image, style: str) -> Image.Image:
    tint = STYLE_TINTS.get(style, STYLE_TINTS["modern"])
    arr = np.asarray(image.convert("RGB")).astype(np.float32)
    arr[..., 0] *= tint[0]
    arr[..., 1] *= tint[1]
    arr[..., 2] *= tint[2]
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    result = Image.fromarray(arr, "RGB")
    if style == "luxury":
        result = ImageEnhance.Contrast(result).enhance(1.08)
        result = ImageEnhance.Color(result).enhance(1.08)
    elif style == "minimalist":
        result = ImageEnhance.Color(result).enhance(0.86)
        result = ImageEnhance.Brightness(result).enhance(1.04)
    elif style == "industrial":
        result = ImageEnhance.Contrast(result).enhance(1.12)
        result = ImageEnhance.Color(result).enhance(0.86)
    elif style == "bohemian":
        result = ImageEnhance.Color(result).enhance(1.16)
    return result


def resize_cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def resize_contain(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    out = image.copy()
    out.thumbnail(size, Image.Resampling.LANCZOS)
    return out


def gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    width, height = size
    y = np.linspace(0, 1, height, dtype=np.float32)[:, None]
    top_arr = np.array(top, dtype=np.float32)
    bottom_arr = np.array(bottom, dtype=np.float32)
    row = top_arr * (1 - y) + bottom_arr * y
    arr = np.repeat(row[:, None, :], width, axis=1).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def make_panorama(source: Image.Image, style: str, room_type: str) -> tuple[Image.Image, dict[str, Any]]:
    src = ImageOps.exif_transpose(source).convert("RGB")
    src = apply_style_tint(src, style)

    pano_w, pano_h = 4096, 2048
    center_w, center_h = 1760, 1220
    center = resize_cover(src, (center_w, center_h))

    blur_base = resize_cover(src, (pano_w, pano_h)).filter(ImageFilter.GaussianBlur(32))
    mirrored = ImageOps.mirror(resize_cover(src, (pano_w, pano_h))).filter(ImageFilter.GaussianBlur(18))
    pano = Image.blend(blur_base, mirrored, 0.28)

    top_color = tuple(np.asarray(src.resize((1, 1), Image.Resampling.BICUBIC)).reshape(3).astype(int))
    top = gradient((pano_w, 420), lighten(top_color, 30), darken(top_color, 12)).filter(ImageFilter.GaussianBlur(4))
    bottom = gradient((pano_w, 440), darken(top_color, 42), darken(top_color, 70)).filter(ImageFilter.GaussianBlur(4))
    pano.paste(top, (0, 0))
    pano.paste(bottom, (0, pano_h - bottom.height))

    x0 = (pano_w - center_w) // 2
    y0 = 430
    mask = Image.new("L", (center_w, center_h), 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.rounded_rectangle((0, 0, center_w, center_h), radius=42, fill=255)
    soft_mask = mask.filter(ImageFilter.GaussianBlur(5))

    shadow = Image.new("RGBA", (center_w + 120, center_h + 120), (0, 0, 0, 0))
    shadow_mask = Image.new("L", (center_w + 120, center_h + 120), 0)
    ImageDraw.Draw(shadow_mask).rounded_rectangle((60, 60, center_w + 60, center_h + 60), radius=52, fill=138)
    shadow.putalpha(shadow_mask.filter(ImageFilter.GaussianBlur(35)))
    pano_rgba = pano.convert("RGBA")
    pano_rgba.alpha_composite(shadow, (x0 - 60, y0 - 60))
    pano_rgba.paste(center.convert("RGBA"), (x0, y0), soft_mask)

    pano = pano_rgba.convert("RGB")
    pano = add_room_lines(pano, x0, y0, center_w, center_h, room_type)
    pano = add_vignette(pano)
    metadata = {
        "projection": "equirectangular",
        "width": pano_w,
        "height": pano_h,
        "source_embed": {"x": x0, "y": y0, "width": center_w, "height": center_h},
        "generation": "local_pillow_panorama_v1",
        "note": "Local deterministic panorama synthesized from a single uploaded photo. No external AI or paid APIs are used.",
    }
    return pano, metadata


def lighten(color: tuple[int, int, int], amount: int) -> tuple[int, int, int]:
    return tuple(min(255, int(c + amount)) for c in color)


def darken(color: tuple[int, int, int], amount: int) -> tuple[int, int, int]:
    return tuple(max(0, int(c - amount)) for c in color)


def add_room_lines(image: Image.Image, x: int, y: int, w: int, h: int, room_type: str) -> Image.Image:
    out = image.convert("RGBA")
    draw = ImageDraw.Draw(out, "RGBA")
    gold = (212, 197, 169, 82)
    soft = (255, 255, 255, 30)
    floor_y = y + h + 40
    ceiling_y = max(260, y - 70)
    vanishing = (x + w // 2, y + h // 2)
    for px in (0, x - 180, x + w + 180, image.width):
        draw.line((vanishing[0], vanishing[1], px, floor_y), fill=soft, width=2)
    draw.line((0, floor_y, image.width, floor_y), fill=gold, width=2)
    draw.line((0, ceiling_y, image.width, ceiling_y), fill=(255, 255, 255, 18), width=1)
    if room_type in {"kitchen", "office"}:
        for px in range(0, image.width, 260):
            draw.line((px, floor_y, px + 130, image.height), fill=(255, 255, 255, 18), width=1)
    elif room_type == "bathroom":
        for px in range(0, image.width, 220):
            draw.line((px, floor_y, px, image.height), fill=(255, 255, 255, 14), width=1)
        for py in range(floor_y, image.height, 150):
            draw.line((0, py, image.width, py), fill=(255, 255, 255, 14), width=1)
    return out.convert("RGB")


def add_vignette(image: Image.Image) -> Image.Image:
    w, h = image.size
    x = np.linspace(-1, 1, w, dtype=np.float32)
    y = np.linspace(-1, 1, h, dtype=np.float32)
    xx, yy = np.meshgrid(x, y)
    dist = np.sqrt(xx * xx + yy * yy)
    mask = np.clip(1.12 - dist * 0.42, 0.72, 1.0)
    arr = np.asarray(image).astype(np.float32)
    arr *= mask[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


def make_thumb(image: Image.Image) -> Image.Image:
    thumb = resize_cover(image, (960, 540))
    return ImageEnhance.Contrast(thumb).enhance(1.04)


def make_report(tour: sqlite3.Row) -> Path:
    path = EXPORTS_DIR / f"{tour['id']}-report.html"
    metadata = json.loads(tour["metadata_json"] or "{}")
    requirements = json.loads(tour["requirements_json"] or "{}")
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>AETHER Report - {escape_html(tour['title'])}</title>
  <style>
    body {{ font-family: Inter, Arial, sans-serif; margin: 40px; color: #1f1f21; }}
    h1 {{ letter-spacing: .05em; }}
    img {{ width: 100%; max-width: 960px; border-radius: 12px; display: block; }}
    code, pre {{ background: #f4f2ee; padding: 12px; border-radius: 8px; white-space: pre-wrap; }}
  </style>
</head>
<body>
  <h1>{escape_html(tour['title'])}</h1>
  <p>{escape_html(room_label(tour['room_type']))} / {escape_html(style_label(tour['style']))}</p>
  <img src="../tours/{tour['id']}/panorama.jpg" alt="Generated panorama">
  <h2>Requirements</h2>
  <pre>{escape_html(json.dumps(requirements, indent=2))}</pre>
  <h2>Generation Metadata</h2>
  <pre>{escape_html(json.dumps(metadata, indent=2))}</pre>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")
    return path


def escape_html(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def room_label(room_type: str) -> str:
    return ROOM_LABELS.get(room_type, room_type.replace("_", " ").title())


def style_label(style: str) -> str:
    return STYLE_LABELS.get(style, style.replace("_", " ").title())


def tour_to_json(row: sqlite3.Row, request: Request | None = None) -> dict[str, Any]:
    result = {
        "id": row["id"],
        "upload_id": row["upload_id"],
        "title": row["title"],
        "room_type": row["room_type"],
        "room_label": room_label(row["room_type"]),
        "style": row["style"],
        "style_label": style_label(row["style"]),
        "requirements": json.loads(row["requirements_json"] or "{}"),
        "metadata": json.loads(row["metadata_json"] or "{}"),
        "saved": bool(row["saved"]),
        "favorite": bool(row["favorite"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "source_url": public_path(Path(row["source_path"])),
        "pano_url": public_path(Path(row["pano_path"])),
        "thumb_url": public_path(Path(row["thumb_path"])),
    }
    if request:
        base = str(request.base_url).rstrip("/")
        for key in ("source_url", "pano_url", "thumb_url"):
            result[key] = base + result[key]
    return result


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "name": "AETHER Local API", "time": utc_now()}


@app.post("/api/auth/register")
def register(payload: RegisterPayload) -> dict[str, Any]:
    email = validate_email(payload.email)
    password = payload.password
    if len(password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters.")
    user_id = new_id("usr")
    salt = secrets.token_hex(16)
    with db() as conn:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="An account with this email already exists.")
        conn.execute(
            """
            INSERT INTO users (id, email, name, password_hash, salt, settings_json, created_at)
            VALUES (?, ?, ?, ?, ?, '{}', ?)
            """,
            (user_id, email, payload.name.strip() or "Designer", hash_password(password, salt), salt, utc_now()),
        )
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    token = create_session(user_id)
    return {"token": token, "user": row_to_user(user)}


@app.post("/api/auth/login")
def login(payload: LoginPayload) -> dict[str, Any]:
    email = validate_email(payload.email)
    with db() as conn:
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not user or not verify_password(payload.password, user["salt"], user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return {"token": create_session(user["id"]), "user": row_to_user(user)}


@app.post("/api/auth/logout")
def logout(authorization: str | None = Header(default=None)) -> dict[str, bool]:
    if authorization:
        token = bearer_token(authorization)
        with db() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash(token),))
    return {"ok": True}


@app.get("/api/me")
def me(user: sqlite3.Row = Depends(current_user)) -> dict[str, Any]:
    with db() as conn:
        stats = conn.execute(
            """
            SELECT COUNT(*) AS projects,
                   SUM(CASE WHEN saved = 1 THEN 1 ELSE 0 END) AS saved,
                   SUM(CASE WHEN favorite = 1 THEN 1 ELSE 0 END) AS favorites
            FROM tours WHERE user_id = ?
            """,
            (user["id"],),
        ).fetchone()
    return {
        "user": row_to_user(user),
        "stats": {
            "projects": int(stats["projects"] or 0),
            "saved": int(stats["saved"] or 0),
            "favorites": int(stats["favorites"] or 0),
        },
    }


@app.patch("/api/me")
def patch_me(payload: ProfilePatch, user: sqlite3.Row = Depends(current_user)) -> dict[str, Any]:
    name = (payload.name or user["name"]).strip() or user["name"]
    settings = json.loads(user["settings_json"] or "{}")
    if payload.settings:
        settings.update(payload.settings)
    with db() as conn:
        conn.execute(
            "UPDATE users SET name = ?, settings_json = ? WHERE id = ?",
            (name, safe_json(settings), user["id"]),
        )
        updated = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    return {"user": row_to_user(updated)}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...), user: sqlite3.Row = Depends(current_user)) -> dict[str, Any]:
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Please upload a JPG or PNG image.")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Image exceeds the 20MB limit.")
    try:
        image = Image.open(io.BytesIO(data))
        image.verify()
        image = Image.open(io.BytesIO(data))
        image = ImageOps.exif_transpose(image).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="The uploaded file is not a readable image.") from exc

    upload_id = new_id("upl")
    target_dir = UPLOADS_DIR / upload_id
    target_dir.mkdir(parents=True, exist_ok=True)
    ext = ".jpg" if content_type in {"image/jpeg", "image/jpg"} else ".png"
    target = target_dir / f"source{ext}"
    if ext == ".jpg":
        image.save(target, "JPEG", quality=92, optimize=True)
    else:
        image.save(target, "PNG", optimize=True)

    with db() as conn:
        conn.execute(
            """
            INSERT INTO uploads (id, user_id, filename, content_type, path, width, height, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                upload_id,
                user["id"],
                file.filename or f"upload{ext}",
                content_type,
                str(target),
                image.width,
                image.height,
                utc_now(),
            ),
        )
    return {
        "uploadId": upload_id,
        "filename": file.filename,
        "width": image.width,
        "height": image.height,
        "url": public_path(target),
    }


@app.post("/api/tours")
def create_tour(payload: TourCreatePayload, user: sqlite3.Row = Depends(current_user)) -> dict[str, Any]:
    style = payload.style.strip().lower().replace(" ", "_") or "modern"
    room_type = payload.roomType.strip().lower().replace(" ", "_") or "living_room"

    with db() as conn:
        upload = conn.execute(
            "SELECT * FROM uploads WHERE id = ? AND user_id = ?",
            (payload.uploadId, user["id"]),
        ).fetchone()
    if not upload:
        raise HTTPException(status_code=404, detail="Uploaded room photo was not found.")

    tour_id = new_id("tour")
    tour_dir = TOURS_DIR / tour_id
    tour_dir.mkdir(parents=True, exist_ok=True)
    source_path = Path(upload["path"])
    source = Image.open(source_path)
    pano, metadata = make_panorama(source, style=style, room_type=room_type)
    pano_path = tour_dir / "panorama.jpg"
    thumb_path = tour_dir / "thumbnail.jpg"
    pano.save(pano_path, "JPEG", quality=91, optimize=True)
    make_thumb(pano).save(thumb_path, "JPEG", quality=88, optimize=True)

    title = f"{style_label(style)} {room_label(room_type)}"
    now = utc_now()
    metadata.update(
        {
            "room_type": room_type,
            "style": style,
            "source_width": upload["width"],
            "source_height": upload["height"],
            "created_at": now,
        }
    )

    with db() as conn:
        conn.execute(
            """
            INSERT INTO tours
              (id, user_id, upload_id, title, room_type, style, requirements_json, metadata_json,
               pano_path, thumb_path, source_path, saved, favorite, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)
            """,
            (
                tour_id,
                user["id"],
                upload["id"],
                title,
                room_type,
                style,
                safe_json(payload.requirements),
                safe_json(metadata),
                str(pano_path),
                str(thumb_path),
                str(source_path),
                now,
                now,
            ),
        )
        row = conn.execute("SELECT * FROM tours WHERE id = ?", (tour_id,)).fetchone()
    return {"tourId": tour_id, "tour": tour_to_json(row)}


@app.get("/api/tours")
def list_tours(request: Request, user: sqlite3.Row = Depends(current_user)) -> dict[str, Any]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM tours WHERE user_id = ? ORDER BY created_at DESC",
            (user["id"],),
        ).fetchall()
    return {"tours": [tour_to_json(row, request) for row in rows]}


@app.get("/api/tours/{tour_id}")
def get_tour(tour_id: str, request: Request, user: sqlite3.Row = Depends(current_user)) -> dict[str, Any]:
    row = find_tour(tour_id, user["id"])
    return {"tour": tour_to_json(row, request)}


@app.post("/api/tours/{tour_id}/save")
def save_tour(tour_id: str, user: sqlite3.Row = Depends(current_user)) -> dict[str, Any]:
    return update_tour_flag(tour_id, user["id"], "saved")


@app.post("/api/tours/{tour_id}/favorite")
def favorite_tour(tour_id: str, user: sqlite3.Row = Depends(current_user)) -> dict[str, Any]:
    return update_tour_flag(tour_id, user["id"], "favorite")


@app.delete("/api/tours/{tour_id}")
def delete_tour(tour_id: str, user: sqlite3.Row = Depends(current_user)) -> dict[str, bool]:
    row = find_tour(tour_id, user["id"])
    with db() as conn:
        conn.execute("DELETE FROM tours WHERE id = ? AND user_id = ?", (tour_id, user["id"]))
    tour_dir = Path(row["pano_path"]).parent
    if tour_dir.exists() and tour_dir.is_relative_to(TOURS_DIR):
        shutil.rmtree(tour_dir, ignore_errors=True)
    return {"ok": True}


@app.get("/api/tours/{tour_id}/export/{kind}")
def export_tour(
    tour_id: str,
    kind: str,
    token: str | None = None,
    authorization: str | None = Header(default=None),
) -> FileResponse:
    raw_token = token or (bearer_token(authorization) if authorization else "")
    if not raw_token:
        raise HTTPException(status_code=401, detail="Missing authorization token.")
    user = user_from_token(raw_token)
    row = find_tour(tour_id, user["id"])
    if kind in {"pano", "image", "hd"}:
        return FileResponse(Path(row["pano_path"]), filename=f"{row['title']}-panorama.jpg", media_type="image/jpeg")
    if kind in {"thumb", "thumbnail"}:
        return FileResponse(Path(row["thumb_path"]), filename=f"{row['title']}-thumbnail.jpg", media_type="image/jpeg")
    if kind in {"report", "pdf"}:
        report = make_report(row)
        return FileResponse(report, filename=f"{row['title']}-report.html", media_type="text/html")
    if kind in {"model", "json"}:
        payload = tour_to_json(row)
        target = EXPORTS_DIR / f"{tour_id}-tour.json"
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return FileResponse(target, filename=f"{row['title']}-tour.json", media_type="application/json")
    raise HTTPException(status_code=404, detail="Unsupported export type.")


def find_tour(tour_id: str, user_id: str) -> sqlite3.Row:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM tours WHERE id = ? AND user_id = ?",
            (tour_id, user_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Tour was not found.")
    return row


def update_tour_flag(tour_id: str, user_id: str, column: str) -> dict[str, Any]:
    if column not in {"saved", "favorite"}:
        raise HTTPException(status_code=400, detail="Invalid flag.")
    row = find_tour(tour_id, user_id)
    new_value = 0 if int(row[column]) else 1
    with db() as conn:
        conn.execute(
            f"UPDATE tours SET {column} = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (new_value, utc_now(), tour_id, user_id),
        )
        updated = conn.execute("SELECT * FROM tours WHERE id = ?", (tour_id,)).fetchone()
    return {"tour": tour_to_json(updated)}


@app.get("/media/{path:path}")
def media(path: str) -> FileResponse:
    target = (DATA_DIR / path).resolve()
    try:
        target.relative_to(DATA_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Media not found.") from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Media not found.")
    media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(target, media_type=media_type, headers=image_response_headers())


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse("/app/")


@app.get("/app")
def app_no_slash() -> RedirectResponse:
    return RedirectResponse("/app/")


@app.exception_handler(404)
def not_found(_request: Request, _exc: HTTPException) -> JSONResponse:
    return JSONResponse({"detail": "Not found."}, status_code=404)


if FRONTEND_DIR.exists():
    app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
