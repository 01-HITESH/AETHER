from __future__ import annotations

import json
import sqlite3
from typing import Any

from ..database import Database, utc_now


class JobsRepository:
    def __init__(self, database: Database):
        self.database = database

    def get(self, job_id: str, user_id: str | None = None) -> sqlite3.Row | None:
        sql = "SELECT * FROM jobs WHERE id = ?"
        args: tuple[Any, ...] = (job_id,)
        if user_id:
            sql += " AND user_id = ?"
            args += (user_id,)
        with self.database.connection() as conn:
            return conn.execute(sql, args).fetchone()

    def list_for_user(self, user_id: str) -> list[sqlite3.Row]:
        with self.database.connection() as conn:
            return conn.execute("SELECT * FROM jobs WHERE user_id=? ORDER BY created_at DESC", (user_id,)).fetchall()

    def claim_next(self) -> sqlite3.Row | None:
        with self.database.connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
            if not row:
                return None
            conn.execute("UPDATE jobs SET status='running', progress=1, started_at=?, attempts=attempts+1 WHERE id=?", (utc_now(), row["id"]))
            return conn.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone()

    def update(self, job_id: str, **values: Any) -> None:
        if not values:
            return
        columns = ", ".join(f"{key}=?" for key in values)
        with self.database.connection() as conn:
            conn.execute(f"UPDATE jobs SET {columns} WHERE id=?", (*values.values(), job_id))

    def cancel(self, job_id: str, user_id: str) -> sqlite3.Row | None:
        row = self.get(job_id, user_id)
        if not row or row["status"] in {"completed", "failed", "cancelled"}:
            return row
        values = {"cancel_requested": 1}
        if row["status"] == "queued":
            values.update(status="cancelled", completed_at=utc_now())
        self.update(job_id, **values)
        return self.get(job_id, user_id)

    def retry(self, job_id: str, user_id: str) -> sqlite3.Row | None:
        row = self.get(job_id, user_id)
        if not row or row["status"] not in {"failed", "cancelled"}:
            return row
        self.update(job_id, status="queued", progress=0, error=None, cancel_requested=0, started_at=None, completed_at=None)
        return self.get(job_id, user_id)


def job_to_dict(row: sqlite3.Row, tours: list[dict] | None = None) -> dict[str, Any]:
    return {
        "id": row["id"], "status": row["status"], "progress": row["progress"], "error": row["error"],
        "provider": row["provider"], "model": row["model"], "prompt": row["prompt"],
        "negativePrompt": row["negative_prompt"], "settings": json.loads(row["settings_json"]),
        "seeds": json.loads(row["seeds_json"]), "variantCount": row["variant_count"],
        "attempts": row["attempts"], "createdAt": row["created_at"], "startedAt": row["started_at"],
        "completedAt": row["completed_at"], "results": tours or [],
    }

