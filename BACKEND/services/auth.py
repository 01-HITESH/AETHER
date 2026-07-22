from __future__ import annotations

import json
import secrets
import smtplib
import sqlite3
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any
from urllib.parse import quote

from fastapi import HTTPException, Request

from ..config import Settings
from ..database import Database, parse_time, utc_after, utc_now
from ..repositories.users import UsersRepository, safe_json
from .security import PasswordService, SecretCipher, new_id, token_hash, verify_totp

try:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token
except ImportError:  # pragma: no cover - optional until Google auth is configured.
    google_requests = None
    google_id_token = None


@dataclass
class SessionContext:
    user: sqlite3.Row
    session: dict[str, Any]
    token_hash: str
    database: Database


class AuthService:
    def __init__(self, settings: Settings, database: Database):
        self.settings = settings
        self.database = database
        self.users = UsersRepository(database)
        self.passwords = PasswordService()
        self.secrets = SecretCipher(settings.secret_key)

    def validate_email(self, email: str) -> str:
        value = email.strip().lower()
        if len(value) > 254 or "@" not in value or value.startswith("@") or value.endswith("@"):
            raise HTTPException(status_code=400, detail="Enter a valid email address.")
        return value

    def validate_password(self, password: str) -> None:
        if len(password) < 10:
            raise HTTPException(status_code=400, detail="Password must be at least 10 characters.")
        if len(password) > 256:
            raise HTTPException(status_code=400, detail="Password is too long.")

    def register(self, name: str, email: str, password: str) -> sqlite3.Row:
        normalized = self.validate_email(email)
        self.validate_password(password)
        if self.users.by_email(normalized):
            raise HTTPException(status_code=409, detail="An account with this email already exists.")
        return self.users.create(
            user_id=new_id("usr"),
            email=normalized,
            name=name.strip() or "Designer",
            password_hash=self.passwords.hash(password),
        )

    def login(self, email: str, password: str, otp: str = "") -> sqlite3.Row:
        normalized = self.validate_email(email)
        user = self.users.by_email(normalized)
        if not user or not self.passwords.verify(password, user["password_hash"], user["salt"]):
            raise HTTPException(status_code=401, detail="Invalid email or password.")
        if bool(user["two_factor_enabled"]):
            secret = self.secrets.decrypt(user["two_factor_secret"])
            if not otp:
                raise HTTPException(
                    status_code=401,
                    detail={"message": "Two-factor code required.", "code": "two_factor_required"},
                )
            if not secret or not verify_totp(secret, otp):
                raise HTTPException(status_code=401, detail="Invalid two-factor code.")
        if self.passwords.needs_rehash(user["password_hash"]):
            self.users.update_password(user["id"], self.passwords.hash(password))
            user = self.users.by_id(user["id"])
        return user

    def create_session(self, user_id: str, request: Request) -> str:
        raw = secrets.token_urlsafe(48)
        now = utc_now()
        digest = token_hash(raw)
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    token_hash, user_id, created_at, expires_at, last_seen_at,
                    revoked_at, user_agent, ip_address
                )
                VALUES (?, ?, ?, ?, ?, '', ?, ?)
                """,
                (
                    digest,
                    user_id,
                    now,
                    utc_after(self.settings.session_ttl_seconds),
                    now,
                    (request.headers.get("user-agent") or "")[:300],
                    (request.client.host if request.client else "")[:80],
                ),
            )
            UsersRepository.log_history(conn, user_id, "signed_in", "Signed in to AETHER.")
        return raw

    def authenticate(self, request: Request) -> SessionContext:
        raw = request.cookies.get(self.settings.cookie_name, "")
        if not raw:
            authorization = request.headers.get("authorization", "")
            scheme, _, candidate = authorization.partition(" ")
            if scheme.lower() == "bearer":
                raw = candidate
        if not raw:
            raise HTTPException(status_code=401, detail="Sign in required.")
        digest = token_hash(raw)
        expired = False
        session: dict[str, Any] | None = None
        with self.database.connect() as conn:
            row = conn.execute(
                """
                SELECT sessions.token_hash AS session_token_hash, sessions.user_id AS session_user_id,
                       sessions.created_at AS session_created_at, sessions.expires_at AS session_expires_at,
                       sessions.last_seen_at AS session_last_seen_at, sessions.revoked_at AS session_revoked_at,
                       sessions.user_agent AS session_user_agent, sessions.ip_address AS session_ip_address,
                       users.*
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = ?
                """,
                (digest,),
            ).fetchone()
            if not row or row["session_revoked_at"]:
                raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")
            expires_at = parse_time(row["session_expires_at"])
            if not expires_at or expires_at.timestamp() <= __import__("time").time():
                conn.execute("DELETE FROM sessions WHERE token_hash = ?", (digest,))
                expired = True
            else:
                conn.execute(
                    "UPDATE sessions SET last_seen_at = ? WHERE token_hash = ?",
                    (utc_now(), digest),
                )
                session = {
                    "token_hash": digest,
                    "user_id": row["session_user_id"],
                    "created_at": row["session_created_at"],
                    "expires_at": row["session_expires_at"],
                    "last_seen_at": row["session_last_seen_at"],
                    "revoked_at": row["session_revoked_at"],
                    "user_agent": row["session_user_agent"],
                    "ip_address": row["session_ip_address"],
                }
        if expired:
            raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")
        if session is None:
            raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")
        return SessionContext(user=row, session=session, token_hash=digest, database=self.database)

    def revoke_session(self, token_digest: str, user_id: str, summary: str = "Signed out of AETHER.") -> None:
        with self.database.connect() as conn:
            conn.execute(
                "UPDATE sessions SET revoked_at = ? WHERE token_hash = ? AND user_id = ?",
                (utc_now(), token_digest, user_id),
            )
            UsersRepository.log_history(conn, user_id, "signed_out", summary)

    def revoke_all_sessions(self, user_id: str) -> None:
        with self.database.connect() as conn:
            conn.execute("UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at = ''", (utc_now(), user_id))
            UsersRepository.log_history(
                conn, user_id, "sessions_revoked", "Revoked all active sessions."
            )

    def list_sessions(self, user_id: str, current_digest: str) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM sessions
                WHERE user_id = ? AND revoked_at = '' AND expires_at > ?
                ORDER BY last_seen_at DESC
                """,
                (user_id, utc_now()),
            ).fetchall()
        return [
            {
                "id": row["token_hash"],
                "current": row["token_hash"] == current_digest,
                "created_at": row["created_at"],
                "last_seen_at": row["last_seen_at"],
                "expires_at": row["expires_at"],
                "user_agent": row["user_agent"],
                "ip_address": row["ip_address"],
            }
            for row in rows
        ]

    def revoke_named_session(self, user_id: str, session_id: str, current_digest: str) -> bool:
        if session_id == current_digest:
            raise HTTPException(status_code=400, detail="Use sign out to revoke the current session.")
        with self.database.connect() as conn:
            result = conn.execute(
                """
                UPDATE sessions SET revoked_at = ?
                WHERE token_hash = ? AND user_id = ? AND revoked_at = ''
                """,
                (utc_now(), session_id, user_id),
            )
            if result.rowcount:
                UsersRepository.log_history(
                    conn, user_id, "session_revoked", "Revoked an active session."
                )
        return bool(result.rowcount)

    def create_password_reset(self, email: str) -> tuple[str | None, str]:
        normalized = self.validate_email(email)
        user = self.users.by_email(normalized)
        generic = "If an account exists, password reset instructions have been sent."
        if not user:
            return None, generic
        raw = secrets.token_urlsafe(48)
        with self.database.connect() as conn:
            conn.execute("DELETE FROM password_resets WHERE user_id = ?", (user["id"],))
            conn.execute(
                """
                INSERT INTO password_resets (token_hash, user_id, created_at, expires_at, used_at)
                VALUES (?, ?, ?, ?, '')
                """,
                (
                    token_hash(raw),
                    user["id"],
                    utc_now(),
                    utc_after(self.settings.password_reset_ttl_seconds),
                ),
            )
        self._send_reset_email(normalized, raw)
        return raw if self.settings.environment in {"development", "testing"} else None, generic

    def confirm_password_reset(self, raw_token: str, new_password: str) -> None:
        self.validate_password(new_password)
        digest = token_hash(raw_token)
        with self.database.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM password_resets
                WHERE token_hash = ? AND used_at = '' AND expires_at > ?
                """,
                (digest, utc_now()),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=400, detail="Reset token is invalid or expired.")
            conn.execute("UPDATE password_resets SET used_at = ? WHERE token_hash = ?", (utc_now(), digest))
        self.users.update_password(row["user_id"], self.passwords.hash(new_password))
        self.revoke_all_sessions(row["user_id"])

    def google_login(self, credential: str) -> sqlite3.Row:
        if not self.settings.google_client_ids:
            raise HTTPException(status_code=503, detail="Google sign-in is not configured.")
        if not google_id_token or not google_requests:
            raise HTTPException(status_code=503, detail="Google authentication dependency is unavailable.")
        claims = None
        for client_id in self.settings.google_client_ids:
            try:
                claims = google_id_token.verify_oauth2_token(
                    credential, google_requests.Request(), client_id
                )
                break
            except ValueError:
                continue
        if not claims or not claims.get("sub") or not claims.get("email") or not claims.get("email_verified"):
            raise HTTPException(status_code=401, detail="Google credential could not be verified.")
        email = self.validate_email(str(claims["email"]))
        google_sub = str(claims["sub"])
        name = (str(claims.get("name") or claims.get("given_name") or "").strip() or email.split("@")[0])[:80]
        avatar = str(claims.get("picture") or "")
        user = self.users.by_google_sub(google_sub)
        if user:
            return self.users.update_google_avatar(user["id"], avatar)
        user = self.users.by_email(email)
        if user:
            if user["google_sub"] and user["google_sub"] != google_sub:
                raise HTTPException(status_code=409, detail="Email is linked to another Google account.")
            return self.users.link_google(user["id"], google_sub, avatar)
        return self.users.create(
            user_id=new_id("usr"),
            email=email,
            name=name,
            password_hash=self.passwords.hash(secrets.token_urlsafe(48)),
            auth_provider="google",
            google_sub=google_sub,
            avatar_url=avatar,
        )

    def user_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        profile_url = f"/api/media/profile/{row['id']}" if row["profile_image_path"] else ""
        return {
            "id": row["id"],
            "email": row["email"],
            "name": row["name"],
            "username": row["name"],
            "auth_provider": row["auth_provider"] or "password",
            "settings": json.loads(row["settings_json"] or "{}"),
            "profile_image_url": profile_url,
            "two_factor_enabled": bool(row["two_factor_enabled"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"] or row["created_at"],
        }

    @staticmethod
    def history_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "type": row["event_type"],
            "summary": row["summary"],
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "created_at": row["created_at"],
        }

    def totp_setup(self, user: sqlite3.Row) -> dict[str, str]:
        from .security import generate_totp_secret

        secret = generate_totp_secret()
        encrypted = self.secrets.encrypt(secret)
        with self.database.connect() as conn:
            conn.execute(
                "UPDATE users SET two_factor_secret = ?, two_factor_enabled = 0, updated_at = ? WHERE id = ?",
                (encrypted, utc_now(), user["id"]),
            )
        label = quote(f"AETHER:{user['email']}")
        issuer = quote("AETHER")
        return {
            "secret": secret,
            "otpauth_uri": f"otpauth://totp/{label}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30",
        }

    def enable_totp(self, user_id: str, code: str) -> sqlite3.Row:
        user = self.users.by_id(user_id)
        secret = self.secrets.decrypt(user["two_factor_secret"])
        if not secret or not verify_totp(secret, code):
            raise HTTPException(status_code=400, detail="The verification code is invalid.")
        return self.users.set_two_factor(user_id, user["two_factor_secret"], True)

    def disable_totp(self, user_id: str, code: str) -> sqlite3.Row:
        user = self.users.by_id(user_id)
        secret = self.secrets.decrypt(user["two_factor_secret"])
        if not secret or not verify_totp(secret, code):
            raise HTTPException(status_code=400, detail="The verification code is invalid.")
        return self.users.set_two_factor(user_id, "", False)

    def _send_reset_email(self, recipient: str, token: str) -> None:
        if not self.settings.smtp_host:
            return
        reset_url = f"http://127.0.0.1:8000/app/#/reset/{token}"
        message = EmailMessage()
        message["Subject"] = "Reset your AETHER password"
        message["From"] = self.settings.smtp_from
        message["To"] = recipient
        message.set_content(
            "A password reset was requested for your AETHER account.\n\n"
            f"Open this link to continue:\n{reset_url}\n\n"
            "The link expires in 30 minutes. Ignore this email if you did not request it."
        )
        try:
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=10) as smtp:
                if self.settings.smtp_use_tls:
                    smtp.starttls()
                if self.settings.smtp_username:
                    smtp.login(self.settings.smtp_username, self.settings.smtp_password)
                smtp.send_message(message)
        except OSError:
            if self.settings.environment != "development":
                raise HTTPException(status_code=503, detail="Password reset email could not be sent.")
