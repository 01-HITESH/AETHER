from __future__ import annotations

import json
import sqlite3
from typing import Any

from ..database import Database, utc_now


class UsersRepository:
    def __init__(self, database: Database):
        self.database = database

    def by_id(self, user_id: str) -> sqlite3.Row | None:
        with self.database.connection() as conn:
            return conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

    def by_email(self, email: str) -> sqlite3.Row | None:
        with self.database.connection() as conn:
            return conn.execute("SELECT * FROM users WHERE email=?", (email.lower(),)).fetchone()

    def log_history(self, user_id: str, action: str, details: str = "") -> None:
        with self.database.connection() as conn:
            conn.execute(
                "INSERT INTO user_history(user_id,action,details,created_at) VALUES(?,?,?,?)",
                (user_id, action, details, utc_now()),
            )


def user_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "username": row["name"],
        "settings": json.loads(row["settings_json"] or "{}"),
        "twoFactorEnabled": bool(row["two_factor_enabled"]),
        "profileImageUrl": f"/api/media/profile/{row['id']}" if row["profile_image_path"] else "",
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }
