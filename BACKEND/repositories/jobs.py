from __future__ import annotations

import json
import sqlite3
from typing import Any

from ..database import Database, utc_now
from .users import safe_json


class JobsRepository:
    def __init__(self, database: Database):
        self.database = database

    def create(self, values: dict[str, Any]) -> sqlite3.Row:
        now = utc_now()
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO generation_jobs (
                    id, user_id, upload_id, state, progress, room_type, style, prompt,
                    negative_prompt, provider, model, variant_count, settings_json,
                    requirements_json, seeds_json, result_tour_ids_json, error, attempts,
                    cancel_requested, created_at, updated_at
                )
                VALUES (?, ?, ?, 'queued', 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', '', 0, 0, ?, ?)
                """,
                (
                    values["id"],
                    values["user_id"],
                    values["upload_id"],
                    values["room_type"],
                    values["style"],
                    values["prompt"],
                    values["negative_prompt"],
                    values["provider"],
                    values["model"],
                    values["variant_count"],
                    safe_json(values["settings"]),
                    safe_json(values["requirements"]),
                    safe_json(values["seeds"]),
                    now,
                    now,
                ),
            )
            return conn.execute("SELECT * FROM generation_jobs WHERE id = ?", (values["id"],)).fetchone()

    def get(self, job_id: str, user_id: str | None = None) -> sqlite3.Row | None:
        with self.database.connect() as conn:
            if user_id:
                return conn.execute(
                    "SELECT * FROM generation_jobs WHERE id = ? AND user_id = ?",
                    (job_id, user_id),
                ).fetchone()
            return conn.execute("SELECT * FROM generation_jobs WHERE id = ?", (job_id,)).fetchone()

    def list_for_user(self, user_id: str, limit: int = 20) -> list[sqlite3.Row]:
        with self.database.connect() as conn:
            return list(
                conn.execute(
                    "SELECT * FROM generation_jobs WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                    (user_id, limit),
                ).fetchall()
            )

    def claim_next(self) -> sqlite3.Row | None:
        with self.database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT * FROM generation_jobs
                WHERE state = 'queued' AND cancel_requested = 0
                ORDER BY created_at ASC
                LIMIT 1
                """
            ).fetchone()
            if not row:
                return None
            now = utc_now()
            updated = conn.execute(
                """
                UPDATE generation_jobs
                SET state = 'running', started_at = CASE WHEN started_at = '' THEN ? ELSE started_at END,
                    updated_at = ?, attempts = attempts + 1
                WHERE id = ? AND state = 'queued'
                """,
                (now, now, row["id"]),
            )
            if updated.rowcount != 1:
                return None
            return conn.execute("SELECT * FROM generation_jobs WHERE id = ?", (row["id"],)).fetchone()

    def update_progress(self, job_id: str, progress: int) -> None:
        with self.database.connect() as conn:
            conn.execute(
                "UPDATE generation_jobs SET progress = ?, updated_at = ? WHERE id = ? AND state = 'running'",
                (min(99, max(1, int(progress))), utc_now(), job_id),
            )

    def add_result(self, job_id: str, tour_id: str, progress: int) -> None:
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT result_tour_ids_json FROM generation_jobs WHERE id = ?", (job_id,)
            ).fetchone()
            result_ids = json.loads(row["result_tour_ids_json"] or "[]")
            if tour_id not in result_ids:
                result_ids.append(tour_id)
            conn.execute(
                """
                UPDATE generation_jobs
                SET result_tour_ids_json = ?, progress = ?, updated_at = ?
                WHERE id = ?
                """,
                (safe_json(result_ids), min(99, max(1, progress)), utc_now(), job_id),
            )

    def complete(self, job_id: str) -> None:
        now = utc_now()
        with self.database.connect() as conn:
            conn.execute(
                """
                UPDATE generation_jobs
                SET state = 'completed', progress = 100, error = '', completed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, now, job_id),
            )

    def fail(self, job_id: str, error: str) -> None:
        with self.database.connect() as conn:
            conn.execute(
                """
                UPDATE generation_jobs
                SET state = 'failed', error = ?, updated_at = ?
                WHERE id = ?
                """,
                (error[:1000], utc_now(), job_id),
            )

    def cancel(self, job_id: str, user_id: str) -> sqlite3.Row | None:
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT * FROM generation_jobs WHERE id = ? AND user_id = ?", (job_id, user_id)
            ).fetchone()
            if not row:
                return None
            state = "cancelled" if row["state"] == "queued" else row["state"]
            conn.execute(
                """
                UPDATE generation_jobs
                SET cancel_requested = 1, state = ?, updated_at = ? WHERE id = ? AND user_id = ?
                """,
                (state, utc_now(), job_id, user_id),
            )
            return conn.execute("SELECT * FROM generation_jobs WHERE id = ?", (job_id,)).fetchone()

    def mark_cancelled(self, job_id: str) -> None:
        with self.database.connect() as conn:
            conn.execute(
                "UPDATE generation_jobs SET state = 'cancelled', updated_at = ? WHERE id = ?",
                (utc_now(), job_id),
            )

    def retry(self, job_id: str, user_id: str) -> sqlite3.Row | None:
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT * FROM generation_jobs WHERE id = ? AND user_id = ?", (job_id, user_id)
            ).fetchone()
            if not row or row["state"] not in {"failed", "cancelled"}:
                return None
            progress = int(len(json.loads(row["result_tour_ids_json"] or "[]")) / row["variant_count"] * 100)
            conn.execute(
                """
                UPDATE generation_jobs
                SET state = 'queued', progress = ?, error = '', cancel_requested = 0,
                    completed_at = '', updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (progress, utc_now(), job_id, user_id),
            )
            return conn.execute("SELECT * FROM generation_jobs WHERE id = ?", (job_id,)).fetchone()
