from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import threading
import time
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(12).replace('-', '').replace('_', '')}"


class PasswordService:
    def __init__(self) -> None:
        self.hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)

    def hash(self, password: str) -> str:
        return self.hasher.hash(password)

    def verify(self, encoded: str, password: str) -> bool:
        try:
            return self.hasher.verify(encoded, password)
        except (VerifyMismatchError, InvalidHashError):
            return False


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_code(secret: str, at_time: int | None = None, period: int = 30) -> str:
    padding = "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(secret.upper() + padding)
    counter = int((at_time or int(time.time())) / period)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 15
    number = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{number:06d}"


def verify_totp(secret: str, code: str, window: int = 1) -> bool:
    now = int(time.time())
    return any(hmac.compare_digest(totp_code(secret, now + offset * 30), code.strip()) for offset in range(-window, window + 1))


@dataclass(frozen=True)
class Limit:
    requests: int
    window_seconds: int


class RateLimiter:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._events: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, limit: Limit) -> bool:
        if not self.enabled:
            return True
        cutoff = time.monotonic() - limit.window_seconds
        with self._lock:
            events = [value for value in self._events.get(key, []) if value >= cutoff]
            if len(events) >= limit.requests:
                self._events[key] = events
                return False
            events.append(time.monotonic())
            self._events[key] = events
            return True

