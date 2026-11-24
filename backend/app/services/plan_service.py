"""Subscription plans, usage limits and plan enforcement."""

from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.core.security import utcnow
from app.db.repositories import Repositories, public
from app.utils.serialization import json_safe


def default_plans(settings: Settings) -> list[dict[str, Any]]:
    """Single source of truth for initial pricing; admins can edit the plans collection."""
    currency = settings.payment_currency
    return [
        {
            "code": "free",
            "name": "Free",
            "description": "Basic screening for individual users.",
            "price_monthly_paise": 0,
            "price_yearly_paise": 0,
            "currency": currency,
            "scan_limit": settings.free_scan_limit,
            "features": ["Basic offer analysis", "Basic message analysis", "Standard risk report"],
            "active": True,
            "popular": False,
        },
        {
            "code": "student",
            "name": "Student",
            "description": "Affordable protection for students, recent graduates and everyday users.",
            "price_monthly_paise": 9900,
            "price_yearly_paise": 99000,
            "currency": currency,
            "scan_limit": settings.student_scan_limit,
            "features": ["Higher scan limits", "PDF reports", "Offer monitoring", "Email alerts"],
            "active": True,
            "popular": True,
        },
        {
            "code": "professional",
            "name": "Professional",
            "description": "Advanced investigation for frequent users and teams.",
            "price_monthly_paise": 29900,
            "price_yearly_paise": 299000,
            "currency": currency,
            "scan_limit": settings.professional_scan_limit,
            "features": ["Advanced domain intelligence", "Detailed reports", "Multiple monitored entities", "Advanced analytics"],
            "active": True,
            "popular": False,
        },
        {
            "code": "university",
            "name": "University",
            "description": "Institutional verification workspace.",
            "price_monthly_paise": 99900,
            "price_yearly_paise": 999000,
            "currency": currency,
            "scan_limit": settings.university_scan_limit,
            "features": ["Organization accounts", "Bulk verification", "Staff accounts", "Institutional reports", "Centralized monitoring"],
            "active": True,
            "popular": False,
        },
        {
            "code": "enterprise",
            "name": "Enterprise",
            "description": "Custom deployment, API access and organisation-wide monitoring.",
            "price_monthly_paise": 0,
            "price_yearly_paise": 0,
            "currency": currency,
            "scan_limit": settings.enterprise_scan_limit,
            "features": ["Custom limits", "API access", "Organization-wide monitoring", "Role-based administration", "Custom reporting"],
            "active": True,
            "popular": False,
        },
    ]


class PlanService:
    def __init__(self, settings: Settings, repos: Repositories) -> None:
        self.settings = settings
        self.repos = repos

    def seed(self) -> None:
        for plan in default_plans(self.settings):
            if not self.repos.plans.find_one({"code": plan["code"]}):
                self.repos.plans.insert({**plan, "created_at": utcnow()})

    def plans(self, active_only: bool = True) -> list[dict[str, Any]]:
        query = {"active": True} if active_only else {}
        docs = self.repos.plans.find(query, sort=[("price_monthly_paise", 1)], limit=50)
        return [json_safe(public(doc)) or {} for doc in docs]

    def plan(self, code: str) -> dict[str, Any] | None:
        doc = self.repos.plans.find_one({"code": code})
        return json_safe(public(doc)) if doc else None

    def ensure_subscription(self, user_id: str, plan_code: str = "free") -> dict[str, Any]:
        sub = self.repos.subscriptions.for_user(user_id)
        if sub:
            return sub
        plan = self.plan(plan_code) or default_plans(self.settings)[0]
        return self.repos.subscriptions.upsert(
            user_id,
            {
                "plan_code": plan.get("code", "free"),
                "status": "active",
                "interval": "monthly",
                "provider": None,
                "scans_used": 0,
                "scan_limit": plan.get("scan_limit", self.settings.free_scan_limit),
                "cancel_at_period_end": False,
                "created_at": utcnow(),
            },
        )

    def subscription_out(self, user_id: str) -> dict[str, Any]:
        sub = self.ensure_subscription(user_id)
        plan = self.plan(str(sub.get("plan_code", "free"))) or {}
        return {
            "id": str(sub.get("_id")),
            "user_id": user_id,
            "plan_code": sub.get("plan_code"),
            "status": sub.get("status"),
            "interval": sub.get("interval"),
            "provider": sub.get("provider"),
            "current_period_end": sub.get("current_period_end"),
            "scans_used": int(sub.get("scans_used") or 0),
            "scan_limit": int(sub.get("scan_limit") or plan.get("scan_limit") or self.settings.free_scan_limit),
            "cancel_at_period_end": bool(sub.get("cancel_at_period_end")),
        }

    def can_scan(self, user_id: str) -> tuple[bool, str]:
        sub = self.ensure_subscription(user_id)
        if str(sub.get("status", "")).lower() not in {"active", "trialing"}:
            return False, "subscription is not active"
        used = int(sub.get("scans_used") or 0)
        limit = int(sub.get("scan_limit") or 0)
        if used >= limit:
            return False, f"monthly scan limit of {limit} reached; upgrade to continue"
        return True, ""

    def consume_scan(self, user_id: str) -> None:
        self.repos.subscriptions.increment_usage(user_id, 1)
