"""User-defined monitoring tasks."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user, get_repositories
from app.core.security import utcnow
from app.db.repositories import Repositories
from app.schemas import MonitoringTaskCreate, MonitoringTaskOut
from app.utils.serialization import doc_out

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


def _out(doc: dict[str, Any]) -> MonitoringTaskOut:
    data = doc_out(doc) or {}
    return MonitoringTaskOut(
        id=str(data["id"]),
        user_id=str(data["user_id"]),
        name=data["name"],
        company_names=data.get("company_names", []),
        job_titles=data.get("job_titles", []),
        source_urls=data.get("source_urls", []),
        keywords=data.get("keywords", []),
        enabled=bool(data.get("enabled", True)),
        notify_email=bool(data.get("notify_email", True)),
        notify_in_app=bool(data.get("notify_in_app", True)),
        created_at=data["created_at"],
        last_run_at=data.get("last_run_at"),
        last_status=data.get("last_status"),
    )


@router.get("", response_model=list[MonitoringTaskOut])
def list_monitoring(
    repos: Repositories = Depends(get_repositories),
    user: dict[str, Any] = Depends(get_current_user),
) -> list[MonitoringTaskOut]:
    return [_out(doc) for doc in repos.monitoring.for_user(str(user["id"]))]


@router.post("", response_model=MonitoringTaskOut, status_code=201)
def create_monitoring(
    payload: MonitoringTaskCreate,
    repos: Repositories = Depends(get_repositories),
    user: dict[str, Any] = Depends(get_current_user),
) -> MonitoringTaskOut:
    if not any([payload.company_names, payload.job_titles, payload.keywords]):
        raise HTTPException(status_code=400, detail="at least one company, job title or keyword is required")
    doc = repos.monitoring.insert(
        {
            **payload.model_dump(),
            "user_id": str(user["id"]),
            "created_at": utcnow(),
            "last_run_at": None,
            "last_status": None,
        }
    )
    repos.audit.log(str(user["id"]), "monitoring.created", target=str(doc["_id"]))
    return _out(doc)


@router.delete("/{monitor_id}")
def delete_monitoring(
    monitor_id: str,
    repos: Repositories = Depends(get_repositories),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    doc = repos.monitoring.for_user_id(str(user["id"]), monitor_id)
    if not doc:
        raise HTTPException(status_code=404, detail="monitoring task not found")
    repos.monitoring.delete(monitor_id)
    repos.audit.log(str(user["id"]), "monitoring.deleted", target=monitor_id)
    return {"status": "deleted"}
