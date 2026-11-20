"""Public platform status, configuration disclosure and admin task triggers."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from app.api.deps import get_app_settings, get_repositories, require_admin
from app.billing.payments import razorpay_mode
from app.core.config import Settings
from app.core.security import utcnow
from app.db.repositories import Repositories
from app.schemas import TaskStatusOut
from app.utils.serialization import json_safe
from app.workers.celery_app import dispatch_task

logger = logging.getLogger(__name__)

VERSION = "1.0.0"

router = APIRouter(tags=["system"])


class TriggerOut(TaskStatusOut):
    task_name: str | None = None


def _integration_flags(settings: Settings) -> dict[str, bool]:
    return {
        "virustotal": bool(settings.virustotal_api_key),
        "google_safe_browsing": bool(settings.google_safebrowsing_api_key),
        "google_web_risk": bool(settings.google_webrisk_api_key),
        "mca_registry": bool(settings.mca_api_url and settings.mca_api_key),
        "rdap": bool(settings.rdap_enabled),
        "dns": bool(settings.dns_enabled),
        "tls": bool(settings.tls_enabled),
        "smtp": bool(settings.smtp_host),
        "sms": bool(settings.sms_provider_url),
        "razorpay": bool(settings.razorpay_key_id and settings.razorpay_key_secret),
        "stripe": bool(settings.stripe_secret_key),
        "approved_job_sources": bool(settings.job_source_urls),
        "cloudflare_turnstile": settings.turnstile_active,
    }


def _redis_status(settings: Settings) -> dict[str, Any]:
    if not settings.celery_enabled:
        return {"broker": "disabled", "configured": False}
    try:
        import redis

        client = redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        client.close()
        return {"broker": "connected", "configured": True}
    except Exception as exc:  # noqa: BLE001 - health endpoint must never fail the request
        return {"broker": "unavailable", "configured": True, "error": type(exc).__name__}


@router.get("/system/config")
def system_config(settings: Settings = Depends(get_app_settings)) -> dict[str, Any]:
    """Non-secret runtime capabilities. Unconfigured integrations are reported as false."""
    integrations = _integration_flags(settings)
    return {
        "app_name": settings.app_name,
        "version": VERSION,
        "environment": settings.environment,
        "integrations": integrations,
        "billing": {
            "razorpay": integrations["razorpay"],
            "razorpay_mode": razorpay_mode(settings.razorpay_key_id),
            "razorpay_webhook": bool(settings.razorpay_webhook_secret),
            "stripe": integrations["stripe"],
            "stripe_webhook": bool(settings.stripe_webhook_secret),
            "currency": settings.payment_currency,
        },
        "features": {
            "external_lookups_require_consent": True,
            "corporate_registry_requires_separate_consent": True,
            "document_uploads": True,
            "job_monitoring": bool(settings.scheduler_enabled),
            "billing_enabled": integrations["razorpay"] or integrations["stripe"],
            "webhook_only_payment_activation": True,
            "demo_mode": bool(getattr(settings, "seed_demo_data", True)) and settings.environment.lower() != "production",
            "remembered_sign_ins": True,
        },
        "upload": {
            "max_mb": settings.max_upload_mb,
            "allowed_mime": list(settings.allowed_upload_mime),
        },
        "support_note": (
            "External intelligence is only performed with explicit consent. "
            "Unconfigured providers are reported as unavailable rather than simulated."
        ),
    }


@router.get("/health")
def api_health(request: Request, settings: Settings = Depends(get_app_settings)) -> dict[str, Any]:
    mongo = getattr(request.app.state, "mongo", None)
    database = mongo.health() if mongo else {"database": "not_ready"}
    degraded = bool(getattr(request.app.state, "in_memory_fallback", False))
    return {
        "status": "degraded" if degraded else "ok",
        "version": VERSION,
        "environment": settings.environment,
        "timestamp": utcnow(),
        "database": database,
        **_redis_status(settings),
        "in_memory_fallback": degraded,
    }


@router.get("/system/tasks/{task_id}", response_model=TaskStatusOut)
def task_status(
    task_id: str,
    repos: Repositories = Depends(get_repositories),
    admin: dict[str, Any] = Depends(require_admin),
) -> TaskStatusOut:
    doc = repos.tasks.get(task_id)
    if not doc:
        return TaskStatusOut(task_id=task_id, status="unknown")
    data = json_safe(doc) or {}
    return TaskStatusOut(
        task_id=task_id,
        status=str(data.get("status", "unknown")),
        result=data.get("result"),
        error=data.get("error"),
    )


def _trigger(name: str, *args: Any) -> TriggerOut:
    try:
        task_id = dispatch_task(name, *args)
    except Exception as exc:  # noqa: BLE001
        logger.exception("could not dispatch task %s", name)
        return TriggerOut(task_id="", status="failed", error=str(exc), task_name=name)
    return TriggerOut(task_id=task_id, status="queued", task_name=name)


@router.post("/system/tasks/monitoring", response_model=TriggerOut)
def trigger_monitoring(admin: dict[str, Any] = Depends(require_admin)) -> TriggerOut:
    return _trigger("app.workers.tasks.run_monitoring")


@router.post("/system/tasks/domain-refresh", response_model=TriggerOut)
def trigger_domain_refresh(admin: dict[str, Any] = Depends(require_admin)) -> TriggerOut:
    return _trigger("app.workers.tasks.refresh_domain_intelligence")


@router.post("/system/tasks/analytics", response_model=TriggerOut)
def trigger_analytics(admin: dict[str, Any] = Depends(require_admin)) -> TriggerOut:
    return _trigger("app.workers.tasks.aggregate_analytics")


@router.post("/system/tasks/health-check", response_model=TriggerOut)
def trigger_health_check(admin: dict[str, Any] = Depends(require_admin)) -> TriggerOut:
    return _trigger("app.workers.tasks.health_check")


@router.post("/system/tasks/retention", response_model=TriggerOut)
def trigger_retention(admin: dict[str, Any] = Depends(require_admin)) -> TriggerOut:
    """Run the configured retention purge immediately (admin/owner only)."""
    return _trigger("app.workers.tasks.cleanup_retention")
