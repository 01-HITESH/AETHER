from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:  # pragma: no cover - exercised only before dependencies are installed.
    Fernet = None
    InvalidToken = ValueError

try:
    from argon2 import PasswordHasher as Argon2Hasher
    from argon2.exceptions import InvalidHashError, VerifyMismatchError
except ImportError:  # pragma: no cover - exercised only before dependencies are installed.
    Argon2Hasher = None
    InvalidHashError = ValueError
    VerifyMismatchError = ValueError


PBKDF2_ITERATIONS = 600_000
LEGACY_PBKDF2_ITERATIONS = 180_000


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(12).replace('-', '').replace('_', '')}"


class PasswordService:
    def __init__(self) -> None:
        self._argon = (
            Argon2Hasher(time_cost=3, memory_cost=65536, parallelism=2, hash_len=32, salt_len=16)
            if Argon2Hasher
            else None
        )

    def hash(self, password: str) -> str:
        if self._argon:
            return self._argon.hash(password)
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("ascii"), PBKDF2_ITERATIONS
        )
        return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${base64.b64encode(digest).decode('ascii')}"

    def verify(self, password: str, encoded: str, legacy_salt: str = "") -> bool:
        if encoded.startswith("$argon2") and self._argon:
            try:
                return self._argon.verify(encoded, password)
            except (VerifyMismatchError, InvalidHashError):
                return False
        if encoded.startswith("pbkdf2_sha256$"):
            try:
                _, raw_iterations, salt, expected = encoded.split("$", 3)
                iterations = int(raw_iterations)
            except (ValueError, TypeError):
                return False
            actual = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), salt.encode("ascii"), iterations
            )
            return hmac.compare_digest(base64.b64encode(actual).decode("ascii"), expected)
        if legacy_salt:
            actual = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                legacy_salt.encode("utf-8"),
                LEGACY_PBKDF2_ITERATIONS,
            )
            return hmac.compare_digest(base64.b64encode(actual).decode("ascii"), encoded)
        return False

    def needs_rehash(self, encoded: str) -> bool:
        if encoded.startswith("$argon2") and self._argon:
            return self._argon.check_needs_rehash(encoded)
        return True


class SecretCipher:
    def __init__(self, secret_key: str):
        key = base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode("utf-8")).digest())
        self._fernet = Fernet(key) if Fernet else None

    def encrypt(self, value: str) -> str:
        if not value:
            return ""
        if not self._fernet:
            return value
        return "fernet:" + self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        if not value:
            return ""
        if not value.startswith("fernet:"):
            return value
        if not self._fernet:
            return ""
        try:
            return self._fernet.decrypt(value[7:].encode("ascii")).decode("utf-8")
        except InvalidToken:
            return ""


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_code(secret: str, at_time: int | None = None, period: int = 30) -> str:
    timestamp = int(at_time if at_time is not None else time.time())
    counter = timestamp // period
    padded = secret.upper() + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{value:06d}"


def verify_totp(secret: str, code: str, window: int = 1) -> bool:
    normalized = "".join(ch for ch in code if ch.isdigit())
    if len(normalized) != 6:
        return False
    now = int(time.time())
    return any(
        hmac.compare_digest(totp_code(secret, now + offset * 30), normalized)
        for offset in range(-window, window + 1)
    )


@dataclass
class Limit:
    requests: int
    window_seconds: int


class RateLimiter:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: Limit) -> int:
        if not self.enabled:
            return 0
        now = time.monotonic()
        cutoff = now - limit.window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit.requests:
                return max(1, int(limit.window_seconds - (now - events[0])))
            events.append(now)
        return 0
