from __future__ import annotations

import sqlite3
from contextlib import contextmanager
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
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.settings.db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        for path in (
            self.settings.database_dir,
            self.settings.uploads_dir,
            self.settings.profile_images_dir,
            self.settings.tours_dir,
            self.settings.exports_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
        self.settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript(SCHEMA)


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  password_hash TEXT NOT NULL, settings_json TEXT NOT NULL DEFAULT '{}',
  profile_image_path TEXT, profile_image_type TEXT,
  two_factor_secret TEXT, two_factor_enabled INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, user_id TEXT NOT NULL,
  created_at TEXT NOT NULL, expires_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
  user_agent TEXT NOT NULL DEFAULT '', ip_address TEXT NOT NULL DEFAULT '',
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE TABLE IF NOT EXISTS password_resets (
  token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires_at TEXT NOT NULL,
  used_at TEXT, created_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS uploads (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, filename TEXT NOT NULL,
  path TEXT NOT NULL, content_type TEXT NOT NULL, width INTEGER NOT NULL,
  height INTEGER NOT NULL, created_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, upload_id TEXT NOT NULL,
  status TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0, error TEXT,
  provider TEXT NOT NULL, model TEXT NOT NULL, prompt TEXT NOT NULL,
  negative_prompt TEXT NOT NULL DEFAULT '', settings_json TEXT NOT NULL DEFAULT '{}',
  seeds_json TEXT NOT NULL DEFAULT '[]', variant_count INTEGER NOT NULL DEFAULT 4,
  cancel_requested INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, started_at TEXT, completed_at TEXT,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY(upload_id) REFERENCES uploads(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at);
CREATE TABLE IF NOT EXISTS tours (
  id TEXT PRIMARY KEY, job_id TEXT, user_id TEXT NOT NULL, upload_id TEXT NOT NULL,
  title TEXT NOT NULL, room_type TEXT NOT NULL, style TEXT NOT NULL,
  variant_index INTEGER NOT NULL DEFAULT 0, seed INTEGER NOT NULL,
  prompt TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
  settings_json TEXT NOT NULL DEFAULT '{}', redesign_path TEXT NOT NULL,
  pano_path TEXT NOT NULL, thumb_path TEXT NOT NULL,
  saved INTEGER NOT NULL DEFAULT 0, favorite INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY(upload_id) REFERENCES uploads(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_tours_user ON tours(user_id, created_at DESC);
CREATE TABLE IF NOT EXISTS shares (
  id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, tour_id TEXT NOT NULL,
  user_id TEXT NOT NULL, password_hash TEXT, expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL, revoked_at TEXT,
  FOREIGN KEY(tour_id) REFERENCES tours(id) ON DELETE CASCADE,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS user_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, action TEXT NOT NULL,
  details TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False

