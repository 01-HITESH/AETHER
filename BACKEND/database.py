from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from .config import Settings


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_after(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings

    def connect(self) -> sqlite3.Connection:
        self.settings.ensure_directories()
        conn = sqlite3.connect(
            self.settings.db_path,
            timeout=10,
            check_same_thread=False,
            factory=ManagedConnection,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    def connection(self) -> Iterator[sqlite3.Connection]:
        with self.connect() as conn:
            yield conn

    def initialize(self) -> None:
        self.settings.ensure_directories()
        self._migrate_legacy_database()
        with self.connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode = WAL;

                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL DEFAULT '',
                    auth_provider TEXT NOT NULL DEFAULT 'password',
                    google_sub TEXT NOT NULL DEFAULT '',
                    avatar_url TEXT NOT NULL DEFAULT '',
                    settings_json TEXT NOT NULL DEFAULT '{}',
                    profile_image_path TEXT NOT NULL DEFAULT '',
                    profile_image_content_type TEXT NOT NULL DEFAULT '',
                    profile_image_width INTEGER NOT NULL DEFAULT 0,
                    profile_image_height INTEGER NOT NULL DEFAULT 0,
                    two_factor_secret TEXT NOT NULL DEFAULT '',
                    two_factor_enabled INTEGER NOT NULL DEFAULT 0,
                    password_changed_at TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL DEFAULT '',
                    last_seen_at TEXT NOT NULL DEFAULT '',
                    revoked_at TEXT NOT NULL DEFAULT '',
                    user_agent TEXT NOT NULL DEFAULT '',
                    ip_address TEXT NOT NULL DEFAULT '',
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

                CREATE TABLE IF NOT EXISTS generation_jobs (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    upload_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    room_type TEXT NOT NULL,
                    style TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    negative_prompt TEXT NOT NULL DEFAULT '',
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    variant_count INTEGER NOT NULL DEFAULT 4,
                    settings_json TEXT NOT NULL DEFAULT '{}',
                    requirements_json TEXT NOT NULL DEFAULT '{}',
                    seeds_json TEXT NOT NULL DEFAULT '[]',
                    result_tour_ids_json TEXT NOT NULL DEFAULT '[]',
                    error TEXT NOT NULL DEFAULT '',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT NOT NULL DEFAULT '',
                    completed_at TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY(upload_id) REFERENCES uploads(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS tours (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    upload_id TEXT NOT NULL,
                    job_id TEXT NOT NULL DEFAULT '',
                    variant_index INTEGER NOT NULL DEFAULT 0,
                    title TEXT NOT NULL,
                    room_type TEXT NOT NULL,
                    style TEXT NOT NULL,
                    prompt TEXT NOT NULL DEFAULT '',
                    seed INTEGER NOT NULL DEFAULT 0,
                    provider TEXT NOT NULL DEFAULT 'local_demo',
                    model TEXT NOT NULL DEFAULT '',
                    settings_json TEXT NOT NULL DEFAULT '{}',
                    requirements_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    redesign_path TEXT NOT NULL DEFAULT '',
                    pano_path TEXT NOT NULL DEFAULT '',
                    thumb_path TEXT NOT NULL DEFAULT '',
                    source_path TEXT NOT NULL DEFAULT '',
                    saved INTEGER NOT NULL DEFAULT 0,
                    favorite INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY(upload_id) REFERENCES uploads(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS password_resets (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS shares (
                    token_hash TEXT PRIMARY KEY,
                    tour_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    password_hash TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    revoked_at TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(tour_id) REFERENCES tours(id) ON DELETE CASCADE,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS user_history (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);
                CREATE INDEX IF NOT EXISTS idx_uploads_user_created ON uploads(user_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_jobs_user_created ON generation_jobs(user_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_jobs_state_created ON generation_jobs(state, created_at);
                CREATE INDEX IF NOT EXISTS idx_tours_user_created ON tours(user_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_tours_user_saved ON tours(user_id, saved, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_user_history_user_created ON user_history(user_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_shares_tour_id ON shares(tour_id);
                """
            )
            self._add_legacy_columns(conn)
            now = utc_now()
            conn.execute("UPDATE users SET updated_at = created_at WHERE updated_at = '' OR updated_at IS NULL")
            conn.execute(
                "UPDATE sessions SET expires_at = ?, last_seen_at = created_at "
                "WHERE expires_at = '' OR expires_at IS NULL",
                (utc_after(self.settings.session_ttl_seconds),),
            )
            conn.execute(
                "UPDATE generation_jobs SET state = 'queued', updated_at = ?, started_at = '' "
                "WHERE state = 'running'",
                (now,),
            )

    def _migrate_legacy_database(self) -> None:
        old = self.settings.legacy_db_path
        new = self.settings.db_path
        if not old.exists() or new.exists() or old.resolve() == new.resolve():
            return
        new.parent.mkdir(parents=True, exist_ok=True)
        src = sqlite3.connect(old)
        dst = sqlite3.connect(new)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _add_legacy_columns(self, conn: sqlite3.Connection) -> None:
        user_columns = {
            "profile_image_path": "TEXT NOT NULL DEFAULT ''",
            "profile_image_content_type": "TEXT NOT NULL DEFAULT ''",
            "profile_image_width": "INTEGER NOT NULL DEFAULT 0",
            "profile_image_height": "INTEGER NOT NULL DEFAULT 0",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
            "auth_provider": "TEXT NOT NULL DEFAULT 'password'",
            "google_sub": "TEXT NOT NULL DEFAULT ''",
            "avatar_url": "TEXT NOT NULL DEFAULT ''",
            "two_factor_secret": "TEXT NOT NULL DEFAULT ''",
            "two_factor_enabled": "INTEGER NOT NULL DEFAULT 0",
            "password_changed_at": "TEXT NOT NULL DEFAULT ''",
        }
        session_columns = {
            "expires_at": "TEXT NOT NULL DEFAULT ''",
            "last_seen_at": "TEXT NOT NULL DEFAULT ''",
            "revoked_at": "TEXT NOT NULL DEFAULT ''",
            "user_agent": "TEXT NOT NULL DEFAULT ''",
            "ip_address": "TEXT NOT NULL DEFAULT ''",
        }
        tour_columns = {
            "job_id": "TEXT NOT NULL DEFAULT ''",
            "variant_index": "INTEGER NOT NULL DEFAULT 0",
            "prompt": "TEXT NOT NULL DEFAULT ''",
            "seed": "INTEGER NOT NULL DEFAULT 0",
            "provider": "TEXT NOT NULL DEFAULT 'local_demo'",
            "model": "TEXT NOT NULL DEFAULT ''",
            "settings_json": "TEXT NOT NULL DEFAULT '{}'",
            "redesign_path": "TEXT NOT NULL DEFAULT ''",
        }
        for column, definition in user_columns.items():
            self._ensure_column(conn, "users", column, definition)
        for column, definition in session_columns.items():
            self._ensure_column(conn, "sessions", column, definition)
        for column, definition in tour_columns.items():
            self._ensure_column(conn, "tours", column, definition)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub ON users(google_sub) WHERE google_sub <> ''")


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


class ManagedConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()
