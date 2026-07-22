from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from ..config import Settings
from ..database import Database, path_is_within, utc_now
from .users import UsersRepository, safe_json


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


def room_label(value: str) -> str:
    return ROOM_LABELS.get(value, value.replace("_", " ").title())


def style_label(value: str) -> str:
    return STYLE_LABELS.get(value, value.replace("_", " ").title())


class ToursRepository:
    def __init__(self, database: Database, settings: Settings):
        self.database = database
        self.settings = settings

    def get(self, tour_id: str, user_id: str | None = None) -> sqlite3.Row | None:
        with self.database.connect() as conn:
            if user_id:
                return conn.execute(
                    "SELECT * FROM tours WHERE id = ? AND user_id = ?", (tour_id, user_id)
                ).fetchone()
            return conn.execute("SELECT * FROM tours WHERE id = ?", (tour_id,)).fetchone()

    def require(self, tour_id: str, user_id: str) -> sqlite3.Row:
        row = self.get(tour_id, user_id)
        if not row:
            raise HTTPException(status_code=404, detail="Design was not found.")
        return row

    def list_for_user(self, user_id: str) -> list[sqlite3.Row]:
        with self.database.connect() as conn:
            return list(
                conn.execute(
                    "SELECT * FROM tours WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
                ).fetchall()
            )

    def create(self, values: dict[str, Any]) -> sqlite3.Row:
        now = utc_now()
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO tours (
                    id, user_id, upload_id, job_id, variant_index, title, room_type, style,
                    prompt, seed, provider, model, settings_json, requirements_json, metadata_json,
                    redesign_path, pano_path, thumb_path, source_path, saved, favorite, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)
                """,
                (
                    values["id"],
                    values["user_id"],
                    values["upload_id"],
                    values["job_id"],
                    values["variant_index"],
                    values["title"],
                    values["room_type"],
                    values["style"],
                    values["prompt"],
                    values["seed"],
                    values["provider"],
                    values["model"],
                    safe_json(values["settings"]),
                    safe_json(values["requirements"]),
                    safe_json(values["metadata"]),
                    values["redesign_path"],
                    values["pano_path"],
                    values["thumb_path"],
                    values["source_path"],
                    now,
                    now,
                ),
            )
            UsersRepository.log_history(
                conn,
                values["user_id"],
                "tour_created",
                f"Generated {values['title']}.",
                {
                    "tour_id": values["id"],
                    "job_id": values["job_id"],
                    "provider": values["provider"],
                    "seed": values["seed"],
                },
            )
            return conn.execute("SELECT * FROM tours WHERE id = ?", (values["id"],)).fetchone()

    def toggle(self, tour_id: str, user_id: str, column: str) -> sqlite3.Row:
        if column not in {"saved", "favorite"}:
            raise HTTPException(status_code=400, detail="Invalid design flag.")
        row = self.require(tour_id, user_id)
        value = 0 if int(row[column]) else 1
        with self.database.connect() as conn:
            conn.execute(
                f"UPDATE tours SET {column} = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (value, utc_now(), tour_id, user_id),
            )
            updated = conn.execute("SELECT * FROM tours WHERE id = ?", (tour_id,)).fetchone()
            UsersRepository.log_history(
                conn,
                user_id,
                f"tour_{column}_{'on' if value else 'off'}",
                f"{'Marked' if value else 'Unmarked'} {updated['title']} as {column}.",
                {"tour_id": tour_id},
            )
            return updated

    def delete(self, tour_id: str, user_id: str) -> None:
        row = self.require(tour_id, user_id)
        with self.database.connect() as conn:
            UsersRepository.log_history(
                conn, user_id, "tour_deleted", f"Deleted {row['title']}.", {"tour_id": tour_id}
            )
            conn.execute("DELETE FROM tours WHERE id = ? AND user_id = ?", (tour_id, user_id))
        tour_dir = Path(row["redesign_path"]).parent
        if tour_dir.exists() and path_is_within(tour_dir, self.settings.tours_dir):
            shutil.rmtree(tour_dir, ignore_errors=True)


def tour_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    tour_id = row["id"]
    upload_id = row["upload_id"]
    return {
        "id": tour_id,
        "upload_id": upload_id,
        "job_id": row["job_id"] or "",
        "variant_index": int(row["variant_index"] or 0),
        "title": row["title"],
        "room_type": row["room_type"],
        "room_label": room_label(row["room_type"]),
        "style": row["style"],
        "style_label": style_label(row["style"]),
        "prompt": row["prompt"] or "",
        "seed": int(row["seed"] or 0),
        "provider": row["provider"] or "local_demo",
        "model": row["model"] or "",
        "settings": json.loads(row["settings_json"] or "{}"),
        "requirements": json.loads(row["requirements_json"] or "{}"),
        "metadata": json.loads(row["metadata_json"] or "{}"),
        "saved": bool(row["saved"]),
        "favorite": bool(row["favorite"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "source_url": f"/api/media/uploads/{upload_id}",
        "redesign_url": f"/api/media/tours/{tour_id}/redesign",
        "pano_url": f"/api/media/tours/{tour_id}/panorama",
        "thumb_url": f"/api/media/tours/{tour_id}/thumbnail",
    }
