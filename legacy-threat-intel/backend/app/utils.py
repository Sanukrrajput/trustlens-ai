"""Shared helpers: time, identifiers, validation, redaction, retries, rate limiting."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import re
import threading
import time
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from typing import Any, Callable, Iterable, TypeVar
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

T = TypeVar("T")

_SECRET_RE = re.compile(
    r"(?i)(password|passwd|pwd|secret|token|api[_-]?key|authorization|bearer)\s*[:=]\s*([^\s,;\"']+)"
)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$",
    re.IGNORECASE,
)
_HASH_RE = re.compile(r"^(md5|sha1|sha256)$", re.IGNORECASE)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_ts(value: Any) -> datetime:
    """Parse MongoDB dates, ISO strings and epoch values into aware UTC datetimes."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return utcnow()
        try:
            return parse_ts(float(text))
        except ValueError:
            pass
        normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
        parsed = datetime.fromisoformat(normalized)
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    return utcnow()


def make_id(prefix: str, *parts: Any) -> str:
    digest = hashlib.sha256("\x1f".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def json_safe(value: Any) -> Any:
    """Convert BSON/datetime values into JSON-serializable equivalents."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return to_iso(value)
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    if isinstance(value, ObjectId):
        return str(value)
    if hasattr(value, "binary"):
        return value.binary.decode("utf-8", errors="replace")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def redact(text: str | None, limit: int = 4000) -> str:
    """Remove credentials and personal identifiers from stored raw records."""
    if not text:
        return ""
    cleaned = _SECRET_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", text)
    cleaned = _EMAIL_RE.sub("[EMAIL_REDACTED]", cleaned)
    return cleaned[:limit]


def constant_time_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def is_private_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return True  # unknown values are treated as non-routable
    return bool(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def validate_indicator(kind: str, value: str) -> dict[str, Any]:
    """Validate and normalize an indicator. Never sends data anywhere."""
    kind = (kind or "").lower().strip()
    raw = (value or "").strip()
    result: dict[str, Any] = {
        "type": kind,
        "value": raw,
        "normalized_value": raw.lower(),
        "valid": False,
        "routable": False,
        "reason": "",
    }
    if not raw:
        result["reason"] = "empty indicator"
        return result

    if kind in {"ipv4", "ipv6", "ip"}:
        try:
            address = ipaddress.ip_address(raw)
        except ValueError:
            result["reason"] = "invalid IP address"
            return result
        result.update(
            type=f"ipv{address.version}",
            normalized_value=str(address),
            valid=True,
            routable=not is_private_ip(str(address)),
        )
        return result

    if kind == "domain":
        candidate = raw.lower().rstrip(".")
        if candidate.startswith("http://") or candidate.startswith("https://"):
            candidate = (urlparse(candidate).hostname or "").lower()
        if not _DOMAIN_RE.match(candidate) or candidate.endswith((".local", ".internal")):
            result["reason"] = "invalid or internal domain"
            return result
        try:
            ipaddress.ip_address(candidate)
            result["reason"] = "value is an IP, not a domain"
            return result
        except ValueError:
            pass
        result.update(normalized_value=candidate, valid=True, routable=True)
        return result

    if kind == "url":
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            result["reason"] = "URL must use http/https with a hostname"
            return result
        host = parsed.hostname.lower().rstrip(".")
        if host.endswith((".local", ".internal")) or host in {"localhost"} or is_private_ip(host):
            result["reason"] = "internal or private URL target"
            return result
        result.update(normalized_value=f"{parsed.scheme}://{host}{parsed.path or '/'}", valid=True, routable=True)
        return result

    if kind in {"hash", "md5", "sha1", "sha256"}:
        parts = raw.split(":", 1)
        algo = kind if kind in {"md5", "sha1", "sha256"} else (parts[0].lower() if len(parts) == 2 else "")
        digest = parts[1] if len(parts) == 2 else raw
        lengths = {"md5": 32, "sha1": 40, "sha256": 64}
        if algo not in lengths or not re.fullmatch(rf"[0-9a-f]{{{lengths[algo]}}}", digest.lower()):
            result["reason"] = "invalid hash format"
            return result
        result.update(type="hash", normalized_value=f"{algo}:{digest.lower()}", valid=True, routable=False)
        return result

    result["reason"] = "unsupported indicator type"
    return result


def retry_with_backoff(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except exceptions as exc:  # noqa: BLE001 - intentional bounded retry
            last_error = exc
            if attempt == attempts:
                break
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            logger.warning("retry attempt=%s delay=%.2fs error=%s", attempt, delay, exc)
            time.sleep(delay)
    assert last_error is not None
    raise last_error


class RateLimiter:
    """Simple thread-safe token bucket for external feed calls."""

    def __init__(self, per_minute: int):
        self.capacity = max(1, int(per_minute or 1))
        self.tokens = float(self.capacity)
        self.updated_at = time.monotonic()
        self._lock = threading.Lock()

    def wait(self, timeout: float = 30.0) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self.updated_at) * self.capacity / 60.0)
                self.updated_at = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))


def chunked(items: Iterable[Any], size: int) -> Iterable[list[Any]]:
    batch: list[Any] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def safe_json_dumps(value: Any) -> str:
    try:
        return json.dumps(json_safe(value), default=str)
    except (TypeError, ValueError):
        return str(value)
