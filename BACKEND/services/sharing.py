from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from ..config import Settings
from ..database import Database, utc_after, utc_now
from ..repositories.tours import ToursRepository, tour_to_dict
from .security import PasswordService, token_hash


class SharingService:
    def __init__(self, settings: Settings, database: Database):
        self.settings = settings
        self.database = database
        self.tours = ToursRepository(database, settings)
        self.passwords = PasswordService()

    def create(self, tour_id: str, user_id: str, expires_hours: int, password: str) -> dict[str, Any]:
        self.tours.require(tour_id, user_id)
        raw = secrets.token_urlsafe(32)
        encoded_password = self.passwords.hash(password) if password else ""
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO shares (
                    token_hash, tour_id, user_id, password_hash, created_at, expires_at, revoked_at
                )
                VALUES (?, ?, ?, ?, ?, ?, '')
                """,
                (
                    token_hash(raw),
                    tour_id,
                    user_id,
                    encoded_password,
                    utc_now(),
                    utc_after(expires_hours * 3600),
                ),
            )
        return {
            "token": raw,
            "url": f"/app/#/share/{raw}",
            "expires_at": utc_after(expires_hours * 3600),
            "password_protected": bool(password),
        }

    def get(self, raw_token: str, password: str = "") -> tuple[Any, Any]:
        with self.database.connect() as conn:
            share = conn.execute(
                """
                SELECT * FROM shares
                WHERE token_hash = ? AND revoked_at = '' AND expires_at > ?
                """,
                (token_hash(raw_token), utc_now()),
            ).fetchone()
        if not share:
            raise HTTPException(status_code=404, detail="Share link is invalid or expired.")
        if share["password_hash"] and not self.passwords.verify(password, share["password_hash"]):
            if not password:
                raise HTTPException(
                    status_code=401,
                    detail={"message": "Share password required.", "code": "share_password_required"},
                )
            raise HTTPException(status_code=401, detail="Incorrect share password.")
        tour = self.tours.get(share["tour_id"])
        if not tour:
            raise HTTPException(status_code=404, detail="Shared design no longer exists.")
        return share, tour

    def shared_tour(self, raw_token: str, password: str = "") -> dict[str, Any]:
        share, tour = self.get(raw_token, password)
        result = tour_to_dict(tour)
        result.update(
            {
                "source_url": f"/api/shares/{raw_token}/media/source",
                "redesign_url": f"/api/shares/{raw_token}/media/redesign",
                "pano_url": f"/api/shares/{raw_token}/media/panorama",
                "thumb_url": f"/api/shares/{raw_token}/media/thumbnail",
            }
        )
        return {
            "tour": result,
            "share": {
                "expires_at": share["expires_at"],
                "password_protected": bool(share["password_hash"]),
            },
        }

    def shared_asset(self, raw_token: str, asset: str, password: str = "") -> Path:
        _share, tour = self.get(raw_token, password)
        columns = {
            "source": "source_path",
            "redesign": "redesign_path",
            "panorama": "pano_path",
            "thumbnail": "thumb_path",
        }
        if asset not in columns:
            raise HTTPException(status_code=404, detail="Media not found.")
        target = Path(tour[columns[asset]])
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Media not found.")
        return target
