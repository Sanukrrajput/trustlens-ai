"""FastAPI dependency providers and API-key authentication."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request, status

from app.config import Settings
from app.db.mongo import MongoDBService
from app.db.repositories import Repositories
from app.utils import constant_time_equals


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_mongo(request: Request) -> MongoDBService:
    return request.app.state.mongo


def get_repos(request: Request) -> Repositories:
    return request.app.state.repos


def get_services(request: Request) -> dict[str, Any]:
    return request.app.state.services


def require_api_key(request: Request, settings: Settings = Depends(get_settings)) -> str:
    if not settings.auth_enabled:
        return "anonymous"
    header = request.headers.get("X-API-Key", "")
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        header = authorization[7:].strip()
    if not header or not constant_time_equals(header, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return "api_key"
