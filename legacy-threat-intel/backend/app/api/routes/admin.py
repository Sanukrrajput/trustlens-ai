"""Notifications, audit logs, response approvals and identity endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_repos, get_services, require_api_key
from app.db.repositories import Repositories
from app.schemas import ResponseActionInput
from app.utils import json_safe

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_api_key)])


@router.get("/me")
def me(api_key: str = Depends(require_api_key)) -> dict[str, Any]:
    return {"authenticated": True, "method": api_key, "permissions": ["read", "investigate", "configure_alerts"]}


@router.get("/notifications")
def list_notifications(
    page: int = 1,
    page_size: int = 25,
    unread_only: bool = False,
    severity: str | None = None,
    repos: Repositories = Depends(get_repos),
) -> dict[str, Any]:
    query: dict[str, Any] = {}
    if unread_only:
        query["read"] = {"$ne": True}
    if severity:
        query["severity"] = severity
    return repos.notifications.paginate(query, page=page, page_size=page_size, sort_field="created_at")


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: str, repos: Repositories = Depends(get_repos)) -> dict[str, Any]:
    modified = repos.notifications.mark_read(notification_id)
    if not modified:
        raise HTTPException(404, "notification not found")
    return {"status": "read", "notification_id": notification_id}


@router.get("/audit-logs")
def list_audit_logs(
    page: int = 1,
    page_size: int = 25,
    q: str | None = None,
    actor: str | None = None,
    repos: Repositories = Depends(get_repos),
) -> dict[str, Any]:
    query: dict[str, Any] = {}
    if actor:
        query["actor"] = actor
    if q:
        query["$or"] = [
            {"action": {"$regex": q, "$options": "i"}},
            {"details": {"$regex": q, "$options": "i"}},
        ]
    return repos.audit.paginate(query, page=page, page_size=page_size, sort_field="timestamp")


@router.post("/response-actions")
def propose_action(
    payload: ResponseActionInput,
    services: dict[str, Any] = Depends(get_services),
) -> dict[str, Any]:
    return json_safe(services["response"].propose(payload.model_dump()))


@router.get("/response-actions")
def list_response_actions(
    repos: Repositories = Depends(get_repos),
) -> dict[str, Any]:
    actions = repos.actions.find({}, sort_field="created_at", limit=100)
    return {"items": json_safe(actions), "total": len(actions)}


@router.post("/response-actions/{action_id}/approve")
def approve_action(
    action_id: str,
    approver: str = "analyst",
    note: str = "",
    services: dict[str, Any] = Depends(get_services),
) -> dict[str, Any]:
    try:
        return json_safe(services["response"].approve(action_id, approver, note))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
