from __future__ import annotations

import json
import sqlite3
from typing import Any

from ..database import Database, utc_now
from ..services.security import new_id


def safe_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True)


class UsersRepository:
    def __init__(self, database: Database):
        self.database = database

    def by_id(self, user_id: str) -> sqlite3.Row | None:
        with self.database.connect() as conn:
            return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def by_email(self, email: str) -> sqlite3.Row | None:
        with self.database.connect() as conn:
            return conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    def by_google_sub(self, google_sub: str) -> sqlite3.Row | None:
        with self.database.connect() as conn:
            return conn.execute("SELECT * FROM users WHERE google_sub = ?", (google_sub,)).fetchone()

    def create(
        self,
        *,
        user_id: str,
        email: str,
        name: str,
        password_hash: str,
        auth_provider: str = "password",
        google_sub: str = "",
        avatar_url: str = "",
    ) -> sqlite3.Row:
        now = utc_now()
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO users (
                    id, email, name, password_hash, salt, auth_provider, google_sub, avatar_url,
                    settings_json, created_at, updated_at, password_changed_at
                )
                VALUES (?, ?, ?, ?, '', ?, ?, ?, '{}', ?, ?, ?)
                """,
                (
                    user_id,
                    email,
                    name,
                    password_hash,
                    auth_provider,
                    google_sub,
                    avatar_url,
                    now,
                    now,
                    now,
                ),
            )
            self.log_history(
                conn,
                user_id,
                "account_created",
                "Created AETHER account.",
                {"email": email, "provider": auth_provider},
            )
            return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def update_password(self, user_id: str, password_hash: str) -> None:
        now = utc_now()
        with self.database.connect() as conn:
            conn.execute(
                """
                UPDATE users
                SET password_hash = ?, salt = '', password_changed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (password_hash, now, now, user_id),
            )
            self.log_history(conn, user_id, "password_updated", "Changed account password.")

    def update_profile(self, user_id: str, name: str, settings: dict[str, Any]) -> sqlite3.Row:
        with self.database.connect() as conn:
            conn.execute(
                "UPDATE users SET name = ?, settings_json = ?, updated_at = ? WHERE id = ?",
                (name, safe_json(settings), utc_now(), user_id),
            )
            self.log_history(conn, user_id, "profile_updated", "Updated account profile settings.")
            return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def set_profile_image(
        self,
        user_id: str,
        *,
        path: str,
        content_type: str,
        width: int,
        height: int,
        filename: str,
        byte_count: int,
    ) -> sqlite3.Row:
        with self.database.connect() as conn:
            conn.execute(
                """
                UPDATE users
                SET profile_image_path = ?, profile_image_content_type = ?,
                    profile_image_width = ?, profile_image_height = ?, updated_at = ?
                WHERE id = ?
                """,
                (path, content_type, width, height, utc_now(), user_id),
            )
            self.log_history(
                conn,
                user_id,
                "profile_image_updated",
                "Uploaded a profile picture.",
                {
                    "filename": filename,
                    "content_type": content_type,
                    "bytes": byte_count,
                    "width": width,
                    "height": height,
                },
            )
            return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def set_two_factor(self, user_id: str, secret: str, enabled: bool) -> sqlite3.Row:
        with self.database.connect() as conn:
            conn.execute(
                "UPDATE users SET two_factor_secret = ?, two_factor_enabled = ?, updated_at = ? WHERE id = ?",
                (secret, 1 if enabled else 0, utc_now(), user_id),
            )
            self.log_history(
                conn,
                user_id,
                "two_factor_enabled" if enabled else "two_factor_disabled",
                "Enabled two-factor authentication." if enabled else "Disabled two-factor authentication.",
            )
            return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def link_google(self, user_id: str, google_sub: str, avatar_url: str) -> sqlite3.Row:
        with self.database.connect() as conn:
            user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            providers = {part for part in (user["auth_provider"] or "").split(",") if part}
            providers.add("google")
            conn.execute(
                """
                UPDATE users SET google_sub = ?, auth_provider = ?, avatar_url = ?, updated_at = ?
                WHERE id = ?
                """,
                (google_sub, ",".join(sorted(providers)), avatar_url, utc_now(), user_id),
            )
            self.log_history(conn, user_id, "google_linked", "Linked Google sign-in to AETHER account.")
            return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def update_google_avatar(self, user_id: str, avatar_url: str) -> sqlite3.Row:
        with self.database.connect() as conn:
            conn.execute(
                "UPDATE users SET avatar_url = ?, updated_at = ? WHERE id = ?",
                (avatar_url, utc_now(), user_id),
            )
            return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def stats_and_history(self, user_id: str) -> tuple[sqlite3.Row, list[sqlite3.Row]]:
        with self.database.connect() as conn:
            stats = conn.execute(
                """
                SELECT COUNT(*) AS projects,
                       SUM(CASE WHEN saved = 1 THEN 1 ELSE 0 END) AS saved,
                       SUM(CASE WHEN favorite = 1 THEN 1 ELSE 0 END) AS favorites
                FROM tours WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
            history = conn.execute(
                "SELECT * FROM user_history WHERE user_id = ? ORDER BY created_at DESC LIMIT 30",
                (user_id,),
            ).fetchall()
        return stats, list(history)

    @staticmethod
    def log_history(
        conn: sqlite3.Connection,
        user_id: str,
        event_type: str,
        summary: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO user_history (id, user_id, event_type, summary, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (new_id("hist"), user_id, event_type, summary, safe_json(metadata or {}), utc_now()),
        )
