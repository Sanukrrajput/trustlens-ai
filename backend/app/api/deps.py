"""FastAPI dependency providers."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Header, HTTPException, Request, status

from app.core.config import Settings, get_settings
from app.core.security import SlidingWindowRateLimiter, decode_token, role_allowed
from app.db.repositories import Repositories, as_id, public

_rate_limiter = SlidingWindowRateLimiter(limit=120)
_bearer_scheme = "bearer"


def get_app_settings() -> Settings:
    return get_settings()


def get_repositories(request: Request) -> Repositories:
    repos = getattr(request.app.state, "repos", None)
    if repos is None:
        raise HTTPException(status_code=503, detail="database not ready")
    return repos


def get_services(request: Request) -> dict[str, Any]:
    return getattr(request.app.state, "services", {}) or {}


def enforce_rate_limit(request: Request, settings: Settings = Depends(get_app_settings)) -> None:
    client = request.client.host if request.client else "unknown"
    if not _rate_limiter.allow(f"{client}:{request.url.path}"):
        raise HTTPException(status_code=429, detail="rate limit exceeded")


def _extract_bearer(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="authentication required")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != _bearer_scheme:
        raise HTTPException(status_code=401, detail="invalid authorization header")
    return parts[1].strip()


def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_app_settings),
    repos: Repositories = Depends(get_repositories),
) -> dict[str, Any]:
    token = _extract_bearer(authorization)
    try:
        payload = decode_token(settings, token, expected_type="access")
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    blacklist = getattr(repos, "blacklist", None)
    if blacklist and blacklist.find_one({"jti": payload.get("jti")}):
        raise HTTPException(status_code=401, detail="token revoked")

    user = repos.users.get(str(payload.get("sub")))
    if not user or not user.get("active", True):
        raise HTTPException(status_code=401, detail="user unavailable")
    return public(user) or {}


def optional_user(
    request: Request,
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_app_settings),
    repos: Repositories = Depends(get_repositories),
) -> dict[str, Any] | None:
    if not authorization:
        return None
    try:
        return get_current_user(request, authorization, settings, repos)
    except HTTPException:
        return None


def require_role(required: str):
    def dependency(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        if not role_allowed(str(user.get("role", "user")), required):
            raise HTTPException(status_code=403, detail="insufficient permissions")
        return user

    return dependency


require_admin = require_role("admin")
require_staff = require_role("staff")
