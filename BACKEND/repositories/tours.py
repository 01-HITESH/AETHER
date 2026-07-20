from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from ..config import Settings
from ..database import Database


class ToursRepository:
    def __init__(self, database: Database, settings: Settings):
        self.database = database
        self.settings = settings

    def get(self, tour_id: str, user_id: str) -> sqlite3.Row | None:
        with self.database.connection() as conn:
            return conn.execute("SELECT * FROM tours WHERE id=? AND user_id=?", (tour_id, user_id)).fetchone()

    def require(self, tour_id: str, user_id: str) -> sqlite3.Row:
        row = self.get(tour_id, user_id)
        if not row:
            raise HTTPException(404, "Design not found.")
        return row

    def list_for_user(self, user_id: str, job_id: str | None = None) -> list[sqlite3.Row]:
        sql, args = "SELECT * FROM tours WHERE user_id=?", [user_id]
        if job_id:
            sql, args = sql + " AND job_id=?", [user_id, job_id]
        with self.database.connection() as conn:
            return conn.execute(sql + " ORDER BY created_at, variant_index", args).fetchall()

    def toggle(self, tour_id: str, user_id: str, column: str) -> sqlite3.Row:
        if column not in {"saved", "favorite"}:
            raise ValueError("Invalid tour flag")
        self.require(tour_id, user_id)
        with self.database.connection() as conn:
            conn.execute(f"UPDATE tours SET {column}=CASE {column} WHEN 1 THEN 0 ELSE 1 END WHERE id=? AND user_id=?", (tour_id, user_id))
        return self.require(tour_id, user_id)

    def delete(self, tour_id: str, user_id: str) -> None:
        row = self.require(tour_id, user_id)
        with self.database.connection() as conn:
            conn.execute("DELETE FROM tours WHERE id=? AND user_id=?", (tour_id, user_id))
        for key in ("redesign_path", "pano_path", "thumb_path"):
            Path(row[key]).unlink(missing_ok=True)


def tour_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"], "jobId": row["job_id"], "title": row["title"], "roomType": row["room_type"],
        "style": row["style"], "variantIndex": row["variant_index"], "seed": row["seed"],
        "prompt": row["prompt"], "provider": row["provider"], "model": row["model"],
        "settings": json.loads(row["settings_json"]), "saved": bool(row["saved"]),
        "favorite": bool(row["favorite"]), "createdAt": row["created_at"],
        "redesignUrl": f"/api/media/tours/{row['id']}/redesign", "panoUrl": f"/api/media/tours/{row['id']}/panorama",
        "thumbnailUrl": f"/api/media/tours/{row['id']}/thumbnail",
    }
