"""Cloudflare Turnstile verification for login challenges.

When credentials are configured the check is authoritative: a missing, invalid
or unverifiable token denies the login. When no keys are configured the platform
reports ``not_configured`` and does not pretend a challenge was performed.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from app.core.config import Settings

logger = logging.getLogger(__name__)

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def verify_turnstile_token(
    settings: Settings,
    token: str | None,
    remote_ip: str | None = None,
) -> dict[str, Any]:
    if not settings.turnstile_active:
        return {"enabled": False, "status": "not_configured", "success": False}
    if not token or len(token) > 4096:
        return {"enabled": True, "status": "missing_token", "success": False}

    body: dict[str, str] = {"secret": settings.turnstile_secret_key, "response": token}
    if remote_ip:
        body["remoteip"] = remote_ip
    try:
        response = requests.post(SITEVERIFY_URL, json=body, timeout=5)
        payload = response.json() if response.content else {}
    except Exception as exc:  # noqa: BLE001 - a provider outage must fail closed
        logger.warning("Turnstile verification unavailable: %s", exc)
        return {"enabled": True, "status": "verification_unavailable", "success": False}

    success = bool(payload.get("success"))
    status = "verified" if success else "rejected"
    if success and settings.turnstile_expected_hostname:
        if payload.get("hostname") != settings.turnstile_expected_hostname:
            success, status = False, "hostname_mismatch"
    return {
        "enabled": True,
        "status": status,
        "success": success,
        "hostname": payload.get("hostname"),
        "error_codes": payload.get("error-codes", []),
    }
