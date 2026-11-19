"""In-app notification endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from app.api.deps import get_current_user, get_repositories
from app.db.repositories import Repositories
from app.schemas import NotificationOut, Paginated
from app.utils.serialization import doc_out

router = APIRouter(prefix="/notifications", tags=["notifications"])


class PreferencesIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    email_alerts: bool | None = None
    in_app_alerts: bool | None = None
    sms_alerts: bool | None = None


def _out(doc: dict[str, Any]) -> NotificationOut:
    data = doc_out(doc) or {}
    return NotificationOut(**data)


@router.get("", response_model=Paginated[NotificationOut])
def list_notifications(
    page: int = 1,
    page_size: int = 20,
    unread_only: bool = False,
    repos: Repositories = Depends(get_repositories),
    user: dict[str, Any] = Depends(get_current_user),
) -> Paginated[NotificationOut]:
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(status_code=400, detail="invalid pagination parameters")
    docs, total = repos.notifications.for_user(
        str(user["id"]), page=page, page_size=page_size, unread_only=unread_only
    )
    import math

    return Paginated(
        items=[_out(doc) for doc in docs],
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, math.ceil(total / page_size)),
    )


@router.patch("/{notification_id}/read", response_model=NotificationOut)
def mark_read(
    notification_id: str,
    repos: Repositories = Depends(get_repositories),
    user: dict[str, Any] = Depends(get_current_user),
) -> NotificationOut:
    doc = repos.notifications.mark_read(str(user["id"]), notification_id)
    if not doc:
        raise HTTPException(status_code=404, detail="notification not found")
    return _out(doc)


@router.put("/preferences")
def update_preferences(
    payload: PreferencesIn,
    repos: Repositories = Depends(get_repositories),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    changes = {key: value for key, value in payload.model_dump().items() if value is not None}
    current = repos.users.get(str(user["id"])) or {}
    preferences = {**(current.get("preferences") or {}), **changes}
    repos.users.update(str(user["id"]), {"preferences": preferences})
    return {"status": "updated", "preferences": preferences}
