"""Authentication, authorisation, token and upload-safety helpers."""

from __future__ import annotations

import hashlib
import hmac
import re
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from jwt.exceptions import PyJWTError as JWTError

from app.core.config import Settings

_password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)

ROLE_HIERarchy = {"user": 0, "student": 0, "staff": 1, "admin": 2, "owner": 3}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_token(
    settings: Settings,
    subject: str,
    token_type: str,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = utcnow()
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "jti": str(uuid.uuid4()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(settings: Settings, subject: str, role: str = "user") -> str:
    return create_token(
        settings,
        subject,
        "access",
        timedelta(minutes=settings.access_token_expire_minutes),
        {"role": role},
    )


def create_refresh_token(settings: Settings, subject: str) -> str:
    return create_token(
        settings,
        subject,
        "refresh",
        timedelta(days=settings.refresh_token_expire_days),
    )


def create_email_token(settings: Settings, subject: str, purpose: str) -> str:
    delta = timedelta(hours=settings.email_verification_expire_hours)
    if purpose == "password_reset":
        delta = timedelta(minutes=settings.password_reset_expire_minutes)
    return create_token(settings, subject, purpose, delta)


def decode_token(settings: Settings, token: str, expected_type: str | None = None) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("invalid or expired token") from exc
    if expected_type and payload.get("type") != expected_type:
        raise ValueError("unexpected token type")
    return payload


def role_allowed(current_role: str, required_role: str) -> bool:
    return ROLE_HIERarchy.get(current_role, -1) >= ROLE_HIERarchy.get(required_role, 99)


def contact_fingerprint(value: str) -> str:
    """Stable pseudonymous fingerprint for correlation; never store raw OTP/bank data."""
    normalised = re.sub(r"\s+", "", value or "").lower()
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def secure_hex_compare(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


class SlidingWindowRateLimiter:
    """In-process limiter suitable for a single API worker; Redis-backed hook can replace it."""

    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and bucket[0] <= now - self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            self._prune_empty()
            return False
        bucket.append(now)
        self._prune_empty()
        return True

    def _prune_empty(self) -> None:
        # A long-lived worker otherwise accumulates one deque per unique key.
        if len(self._hits) > 10_000:
            for key, bucket in list(self._hits.items()):
                if not bucket:
                    self._hits.pop(key, None)


SAFE_MIME_TO_SUFFIX = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "text/plain": ".txt",
}

MIME_MAGIC = {
    "application/pdf": [b"%PDF-"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/webp": [b"RIFF"],
    "text/plain": [],
}


def validate_upload(filename: str, declared_mime: str, content: bytes, settings: Settings) -> tuple[str, str]:
    """Validate size, MIME allowlist and magic bytes. Returns (safe_suffix, detected_mime)."""
    if len(content) == 0:
        raise ValueError("uploaded file is empty")
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise ValueError(f"uploaded file exceeds {settings.max_upload_mb} MB")
    if declared_mime not in settings.allowed_upload_mime:
        raise ValueError(f"unsupported MIME type: {declared_mime}")
    magic = MIME_MAGIC.get(declared_mime, [])
    if magic and not any(content.startswith(prefix) for prefix in magic):
        raise ValueError("file content does not match its declared MIME type")
    if declared_mime == "image/webp" and not content[8:12] == b"WEBP":
        raise ValueError("file content does not match its declared MIME type")
    suffix = SAFE_MIME_TO_SUFFIX[declared_mime]
    safe_name = Path(filename or "upload").name
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", safe_name)[:120]
    if not safe_name.endswith(suffix):
        safe_name += suffix
    return suffix, safe_name


def mask_secrets(values: Iterable[str]) -> list[str]:
    return ["***" if value else "" for value in values]
