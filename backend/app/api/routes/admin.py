"""Administrative dashboards and controls (admin/owner only)."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, model_validator

from app.api.deps import get_app_settings, get_repositories, require_admin
from app.core.config import Settings
from app.core.security import ROLE_HIERarchy, create_email_token, hash_password, utcnow
from app.db.repositories import Repositories, public
from app.schemas import UserOut
from app.services.community_service import STATE_AUDIT_ACTION, STATE_TO_STATUS, apply_moderation
from app.services.notification_service import NotificationService
from app.services.plan_service import PlanService
from app.utils.serialization import json_safe

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["administration"])


class RoleChange(BaseModel):
    role: str = Field(min_length=2, max_length=32)


class AdminUserCreate(BaseModel):
    """Create a named account directly from the admin console.

    Owner is deliberately excluded: it is a break-glass role that must be seeded
    or granted explicitly by an existing owner, never by routine account creation.
    """

    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=2, max_length=120)
    organisation: str | None = Field(default=None, max_length=160)
    role: str = Field(default="user", min_length=2, max_length=32)


class ActiveChange(BaseModel):
    active: bool


class PlanChange(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    price_monthly_paise: int | None = Field(default=None, ge=0)
    price_yearly_paise: int | None = Field(default=None, ge=0)
    scan_limit: int | None = Field(default=None, ge=1)
    features: list[str] | None = Field(default=None, max_length=30)
    active: bool | None = None
    popular: bool | None = None


class ReportReview(BaseModel):
    """Moderator decision. Legacy ``status`` remains accepted for compatibility.

    ``status='reviewed'`` deliberately maps to the pending moderation state: it
    records that a report was seen, not that its allegation was verified.
    """

    status: str | None = Field(default=None, pattern="^(reviewed|dismissed|actioned)$")
    moderation_state: str | None = Field(
        default=None,
        pattern="^(pending|verified|corroborated|false_report|dismissed)$",
    )
    review_notes: str | None = Field(default=None, max_length=2000)
    false_report_reason: str | None = Field(default=None, max_length=1000)


    @model_validator(mode="after")
    def requires_decision(self) -> "ReportReview":
        if not self.status and not self.moderation_state:
            raise ValueError("status or moderation_state is required")
        return self


def _pair_list(counts: dict[str, int]) -> list[dict[str, Any]]:
    return [{"name": name or "unknown", "value": value} for name, value in sorted(counts.items(), key=lambda row: -row[1])]


def _grouped(documents: list[dict[str, Any]], getter) -> dict[str, int]:
    counts: dict[str, int] = {}
    for doc in documents:
        key = str(getter(doc) or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return counts


@router.get("/dashboard")
def dashboard(
    repos: Repositories = Depends(get_repositories),
    admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    documents = repos.analyses.find({}, limit=10_000)
    cutoff = utcnow() - timedelta(hours=24)
    usage = repos.api_usage.find({"updated_at": {"$gte": cutoff}}, limit=10_000)
    daily: dict[str, int] = {}
    for doc in documents:
        created = doc.get("created_at")
        if hasattr(created, "date"):
            day = created.date().isoformat()
            daily[day] = daily.get(day, 0) + 1
    return {
        "total_users": repos.users.count(),
        "total_analyses": repos.analyses.count(),
        "high_risk_count": repos.analyses.count({"risk.score": {"$gte": 60}}),
        "inconclusive_count": repos.analyses.count({"risk.inconclusive": True}),
        "api_requests_24h": sum(int(row.get("count") or 0) for row in usage),
        "scans_by_type": _pair_list(_grouped(documents, lambda doc: doc.get("analysis_type"))),
        "risk_distribution": _pair_list(
            _grouped(documents, lambda doc: (doc.get("risk") or {}).get("category"))
        ),
        "daily_scans": [{"date": day, "count": count} for day, count in sorted(daily.items())],
        "generated_at": utcnow(),
    }


@router.get("/users")
def list_users(
    page: int = 1,
    page_size: int = 20,
    repos: Repositories = Depends(get_repositories),
    admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(status_code=400, detail="invalid pagination parameters")
    docs = repos.users.find({}, sort=[("created_at", -1)], skip=(page - 1) * page_size, limit=page_size)
    items: list[dict[str, Any]] = []
    for doc in docs:
        data = public(doc) or {}
        data.pop("password_hash", None)
        data.pop("consent", None)
        sub = repos.subscriptions.for_user(str(data.get("id")))
        data["subscription"] = {
            "plan_code": sub.get("plan_code") if sub else "free",
            "status": sub.get("status") if sub else "inactive",
            "scans_used": sub.get("scans_used", 0) if sub else 0,
        }
        items.append(json_safe(data) or data)
    return {"items": items, "total": repos.users.count(), "page": page, "page_size": page_size}


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: AdminUserCreate,
    settings: Settings = Depends(get_app_settings),
    repos: Repositories = Depends(get_repositories),
    admin: dict[str, Any] = Depends(require_admin),
) -> UserOut:
    """Create a user, staff or admin account. Requires admin/owner privileges."""
    role = payload.role.lower().strip()
    allowed_roles = {"user", "student", "staff", "admin"}
    if role not in allowed_roles:
        raise HTTPException(
            status_code=400,
            detail="role must be user, student, staff or admin; owner accounts are not created here",
        )
    if ROLE_HIERarchy.get(role, -1) > ROLE_HIERarchy.get(str(admin.get("role")), 0):
        raise HTTPException(status_code=403, detail="cannot create an account above your own role")

    email = payload.email.lower().strip()
    if repos.users.get_by_email(email):
        raise HTTPException(status_code=409, detail="an account with this email already exists")

    admin_id = str(admin["id"])
    user = repos.users.create(
        {
            "email": email,
            "password_hash": hash_password(payload.password),
            "full_name": payload.full_name.strip(),
            "organisation": payload.organisation.strip() if payload.organisation else None,
            "role": role,
            "active": True,
            "email_verified": False,
            "created_at": utcnow(),
            "created_by": admin_id,
            "preferences": {"email_alerts": True, "in_app_alerts": True, "sms_alerts": False},
            "consent": {
                "privacy": True,
                "terms": True,
                "recorded_at": utcnow(),
                "created_by_admin": admin_id,
            },
        }
    )
    user_id = str(user["_id"])
    PlanService(settings, repos).ensure_subscription(user_id)
    repos.audit.log(
        admin_id,
        "admin.user_created",
        target=user_id,
        metadata={"role": role, "email": email},
    )

    token = create_email_token(settings, user_id, "verify_email")
    verify_link = f"{settings.cors_origins[0]}/verify-email?token={token}"
    NotificationService(settings, repos).send_email(
        email,
        "Your TrustLens AI account was created",
        f"An administrator created your account. Verify your email address: {verify_link}",
    )
    return UserOut.model_validate(public(user))


@router.patch("/users/{user_id}/role")
def change_role(
    user_id: str,
    payload: RoleChange,
    repos: Repositories = Depends(get_repositories),
    admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    if payload.role not in ROLE_HIERarchy:
        raise HTTPException(status_code=400, detail="unknown role")
    if ROLE_HIERarchy[payload.role] > ROLE_HIERarchy.get(str(admin.get("role")), 0):
        raise HTTPException(status_code=403, detail="cannot grant a role above your own")
    target = repos.users.get(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="user not found")
    repos.users.set_role(user_id, payload.role)
    repos.audit.log(str(admin["id"]), "admin.user_role_changed", target=user_id, metadata={"role": payload.role})
    return {"status": "updated", "user_id": user_id, "role": payload.role}


@router.patch("/users/{user_id}/active")
def set_active(
    user_id: str,
    payload: ActiveChange,
    repos: Repositories = Depends(get_repositories),
    admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    target = repos.users.get(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="user not found")
    if str(target.get("role")) == "owner" and not payload.active:
        raise HTTPException(status_code=403, detail="owner accounts cannot be disabled here")
    repos.users.update(user_id, {"active": payload.active})
    repos.audit.log(str(admin["id"]), "admin.user_active_changed", target=user_id, metadata={"active": payload.active})
    return {"status": "updated", "user_id": user_id, "active": payload.active}


@router.get("/audit-logs")
def audit_logs(
    page: int = 1,
    page_size: int = 20,
    action: str | None = None,
    repos: Repositories = Depends(get_repositories),
    admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(status_code=400, detail="invalid pagination parameters")
    query = {"action": {"$regex": action, "$options": "i"}} if action else {}
    docs = repos.audit.find(query, sort=[("created_at", -1)], skip=(page - 1) * page_size, limit=page_size)
    return {
        "items": [json_safe(public(doc) or {}) or {} for doc in docs],
        "total": repos.audit.count(query),
        "page": page,
        "page_size": page_size,
    }


@router.get("/models")
def list_models(
    repos: Repositories = Depends(get_repositories),
    admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    versions = repos.models.all_versions()
    return {
        "items": [json_safe(public(doc) or {}) or {} for doc in versions],
        "active": [json_safe(public(doc) or {}) or {} for doc in versions if doc.get("active")],
    }


@router.get("/reports")
def list_user_reports(
    repos: Repositories = Depends(get_repositories),
    admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    docs = repos.user_reports.find({}, sort=[("created_at", -1)], limit=200)
    return {"items": [json_safe(public(doc) or {}) or {} for doc in docs], "total": len(docs)}


@router.patch("/reports/{report_id}")
def review_user_report(
    report_id: str,
    payload: ReportReview,
    repos: Repositories = Depends(get_repositories),
    admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    outcome, updated, previous_state, new_state = apply_moderation(
        repos=repos,
        report_id=report_id,
        admin_id=str(admin["id"]),
        status=payload.status,
        moderation_state=payload.moderation_state,
        review_notes=payload.review_notes,
        false_report_reason=payload.false_report_reason,
    )
    if outcome == "not_found":
        raise HTTPException(status_code=404, detail="report not found")
    if outcome == "invalid_transition":
        raise HTTPException(status_code=409, detail=f"invalid moderation transition: {previous_state} -> {new_state}")
    if outcome == "reason_required":
        raise HTTPException(status_code=400, detail="a false_report_reason is required for false reports")

    metadata = {
        "previous_state": previous_state,
        "moderation_state": new_state,
        "status": payload.status or STATE_TO_STATUS.get(new_state),
        "review_notes": payload.review_notes,
        "false_report_reason": payload.false_report_reason,
    }
    repos.audit.log(str(admin["id"]), "admin.report_reviewed", target=report_id, metadata=metadata)
    repos.audit.log(
        str(admin["id"]),
        STATE_AUDIT_ACTION.get(new_state, "admin.report_reviewed"),
        target=report_id,
        metadata=metadata,
    )
    return json_safe(public(updated) or {}) or {}


@router.get("/plans")
def list_all_plans(
    repos: Repositories = Depends(get_repositories),
    admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    docs = repos.plans.find({}, sort=[("price_monthly_paise", 1)], limit=50)
    return {"items": [json_safe(public(doc) or {}) or {} for doc in docs]}


@router.patch("/plans/{code}")
def update_plan(
    code: str,
    payload: PlanChange,
    settings: Settings = Depends(get_app_settings),
    repos: Repositories = Depends(get_repositories),
    admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    plan = repos.plans.find_one({"code": code})
    if not plan:
        raise HTTPException(status_code=404, detail="plan not found")
    changes = {key: value for key, value in payload.model_dump().items() if value is not None}
    if not changes:
        raise HTTPException(status_code=400, detail="no changes supplied")
    updated = repos.plans.update(str(plan["_id"]), changes)
    repos.audit.log(str(admin["id"]), "admin.plan_updated", target=code, metadata=changes)
    return json_safe(public(updated) or {}) or {}


@router.get("/config")
def platform_config(
    settings: Settings = Depends(get_app_settings),
    admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    return settings.public_dict()


@router.get("/tasks")
def recent_tasks(
    repos: Repositories = Depends(get_repositories),
    admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    docs = repos.tasks.find({}, sort=[("updated_at", -1)], limit=50)
    return {"items": [json_safe(public(doc) or {}) or {} for doc in docs]}
