from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "BACKEND" / "data" / "database" / "aether.sqlite3"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only AETHER user/account inspection utility."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        help=f"Path to aether.sqlite3. Default: {DB_PATH}",
    )
    parser.add_argument("--email", help="Limit output to one user email address.")
    parser.add_argument(
        "--show-projects",
        action="store_true",
        help="Include each user's generated design projects.",
    )
    parser.add_argument(
        "--history-limit",
        type=int,
        default=5,
        help="Number of recent account-history events to show per user.",
    )
    parser.add_argument(
        "--include-credential-hashes",
        action="store_true",
        help="Include stored password hash and salt metadata. Plain-text passwords are never stored.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser.parse_args()


def connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise SystemExit(
            f"Database not found: {db_path}\n"
            "Start the app and register at least one user first."
        )
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def decode_json(value: str | None) -> dict[str, Any]:
    try:
        return json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}


def load_users(conn: sqlite3.Connection, email: str | None, include_hashes: bool) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = ""
    if email:
        where = "WHERE lower(u.email) = lower(?)"
        params.append(email.strip())

    rows = conn.execute(
        f"""
        SELECT
          u.id,
          u.email,
          u.name,
          u.settings_json,
          u.profile_image_path,
          u.created_at,
          u.updated_at,
          u.password_hash,
          u.salt,
          (SELECT COUNT(*) FROM sessions s WHERE s.user_id = u.id) AS active_sessions,
          (SELECT COUNT(*) FROM uploads up WHERE up.user_id = u.id) AS uploads,
          (SELECT COUNT(*) FROM tours t WHERE t.user_id = u.id) AS projects,
          (SELECT COUNT(*) FROM tours t WHERE t.user_id = u.id AND t.saved = 1) AS saved_projects,
          (SELECT COUNT(*) FROM tours t WHERE t.user_id = u.id AND t.favorite = 1) AS favorite_projects,
          (
            SELECT created_at
            FROM user_history h
            WHERE h.user_id = u.id
            ORDER BY h.created_at DESC
            LIMIT 1
          ) AS latest_activity_at
        FROM users u
        {where}
        ORDER BY u.created_at DESC
        """,
        params,
    ).fetchall()

    users: list[dict[str, Any]] = []
    for row in rows:
        item = row_dict(row)
        password_hash = item.pop("password_hash")
        salt = item.pop("salt")
        item["settings"] = decode_json(item.pop("settings_json"))
        item["credential_status"] = "plain-text passwords are not stored"
        item["password_storage"] = "PBKDF2-HMAC-SHA256 salted hash"
        if include_hashes:
            item["credential_hashes"] = {
                "password_hash": password_hash,
                "password_hash_length": len(password_hash or ""),
                "salt": salt,
                "salt_length": len(salt or ""),
            }
        users.append(item)
    return users


def load_projects(conn: sqlite3.Connection, user_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, title, room_type, style, saved, favorite, created_at, updated_at
        FROM tours
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (user_id,),
    ).fetchall()
    projects = []
    for row in rows:
        project = row_dict(row)
        project["saved"] = bool(project["saved"])
        project["favorite"] = bool(project["favorite"])
        projects.append(project)
    return projects


def load_history(conn: sqlite3.Connection, user_id: str, limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    rows = conn.execute(
        """
        SELECT event_type, summary, metadata_json, created_at
        FROM user_history
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    history = []
    for row in rows:
        event = row_dict(row)
        event["metadata"] = decode_json(event.pop("metadata_json"))
        history.append(event)
    return history


def render_text(users: list[dict[str, Any]]) -> str:
    if not users:
        return "No users found."

    lines: list[str] = []
    for user in users:
        lines.append(f"{user['name']} <{user['email']}>")
        lines.append(f"  id: {user['id']}")
        lines.append(f"  created: {user['created_at']}")
        lines.append(f"  updated: {user['updated_at']}")
        lines.append(f"  active sessions: {user['active_sessions']}")
        lines.append(
            "  projects: "
            f"{user['projects']} total, {user['saved_projects']} saved, "
            f"{user['favorite_projects']} favorites"
        )
        lines.append(f"  uploads: {user['uploads']}")
        lines.append(f"  credential status: {user['credential_status']}")
        if "credential_hashes" in user:
            hashes = user["credential_hashes"]
            lines.append(f"  password hash: {hashes['password_hash']}")
            lines.append(f"  salt: {hashes['salt']}")
        if user.get("projects_detail"):
            lines.append("  project detail:")
            for project in user["projects_detail"]:
                flags = []
                if project["saved"]:
                    flags.append("saved")
                if project["favorite"]:
                    flags.append("favorite")
                suffix = f" ({', '.join(flags)})" if flags else ""
                lines.append(
                    f"    - {project['title']} [{project['id']}] "
                    f"{project['room_type']}/{project['style']}{suffix}"
                )
        if user.get("history"):
            lines.append("  recent history:")
            for event in user["history"]:
                lines.append(f"    - {event['created_at']}: {event['summary']}")
        lines.append("")
    return "\n".join(lines).rstrip()


def main() -> int:
    args = parse_args()
    with connect(args.db) as conn:
        users = load_users(conn, args.email, args.include_credential_hashes)
        for user in users:
            if args.show_projects:
                user["projects_detail"] = load_projects(conn, user["id"])
            user["history"] = load_history(conn, user["id"], args.history_limit)

    if args.json:
        print(json.dumps({"users": users}, indent=2, ensure_ascii=True))
    else:
        print(render_text(users))
    return 0


if __name__ == "__main__":
    sys.exit(main())
