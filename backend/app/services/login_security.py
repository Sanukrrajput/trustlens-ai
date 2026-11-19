"""Device and address helpers for remembered sign-in events.

Device identifiers are random browser-generated strings. Only a keyed hash is
persisted so a database leak cannot be replayed as a trusted-device token.
"""

from __future__ import annotations

import hashlib
import ipaddress
from typing import Any

from app.core.config import Settings
from app.schemas import SigninEventOut, SigninSummary

BROWSER_MARKERS = (
    ("Edg/", "Edge"),
    ("OPR/", "Opera"),
    ("Firefox/", "Firefox"),
    ("Chrome/", "Chrome"),
    ("Safari/", "Safari"),
)
PLATFORM_MARKERS = (
    ("Windows NT", "Windows"),
    ("Mac OS X", "macOS"),
    ("Android", "Android"),
    ("iPhone", "iOS"),
    ("iPad", "iOS"),
    ("Linux", "Linux"),
)


def device_hash(settings: Settings, device_id: str | None) -> str | None:
    if not device_id:
        return None
    return hashlib.sha256(f"{settings.secret_key}:{device_id}".encode("utf-8")).hexdigest()


def device_label(user_agent: str | None) -> str:
    if not user_agent:
        return "Unknown device"
    browser = next((name for marker, name in BROWSER_MARKERS if marker in user_agent), "Browser")
    platform = next((name for marker, name in PLATFORM_MARKERS if marker in user_agent), "unknown platform")
    return f"{browser} on {platform}"


def mask_ip(ip: str | None) -> str | None:
    """Redact host bits so the UI can show context without exposing a full address."""
    if not ip:
        return None
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv4Address):
        parts = ip.split(".")
        return ".".join([*parts[:3], "x"]) if len(parts) == 4 else "redacted"
    return "redacted"


def signin_summary(event: dict[str, Any]) -> SigninSummary:
    return SigninSummary(
        at=event["created_at"],
        device=str(event.get("device_label") or "Unknown device"),
        ip_masked=mask_ip(event.get("ip")),
        country=event.get("country"),
    )


def signin_event_out(event: dict[str, Any]) -> SigninEventOut:
    data = signin_summary(event)
    return SigninEventOut(
        id=str(event["_id"]),
        at=data.at,
        device=data.device,
        ip_masked=data.ip_masked,
        country=data.country,
        known_device=bool(event.get("known_device")),
        verification=str(event.get("verification") or "not_configured"),
    )
