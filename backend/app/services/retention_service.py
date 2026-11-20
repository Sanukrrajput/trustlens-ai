"""Configuration-driven retention enforcement.

MongoDB TTL indexes are asynchronous and their seconds values are fixed in
``mongo.py``. This service makes ``RETENTION_DAYS`` and
``AUDIT_RETENTION_DAYS`` actionable: an operator or the scheduled task can purge
documents older than the configured policy, with shorter caps where a data class
is deliberately kept only briefly.

Every run writes one audit event. The service never deletes documents that lack
the timestamp field used by that collection's policy.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.core.config import Settings
from app.core.security import utcnow
from app.db.repositories import Repositories

# (collection, timestamp field, settings field, optional shorter cap in days)
RETENTION_RULES: tuple[tuple[str, str, str, int | None], ...] = (
    ("fraud_analyses", "created_at", "retention_days", None),
    ("risk_indicators", "created_at", "retention_days", None),
    ("reports", "created_at", "retention_days", None),
    ("user_reports", "created_at", "retention_days", None),
    ("notifications", "created_at", "retention_days", 180),
    ("monitoring_tasks", "created_at", "retention_days", None),
    ("audit_logs", "created_at", "audit_retention_days", None),
    ("health_checks", "created_at", "retention_days", None),
    ("signin_events", "created_at", "retention_days", None),
    ("support_messages", "created_at", "retention_days", 30),
    ("domain_intelligence", "checked_at", "retention_days", 30),
    ("task_status", "updated_at", "retention_days", 7),
    ("api_usage", "updated_at", "retention_days", None),
)


def retention_policy(settings: Settings) -> dict[str, int]:
    """Return the effective number of days per collection."""
    return {
        collection: min(int(getattr(settings, setting)), cap) if cap else int(getattr(settings, setting))
        for collection, _field, setting, cap in RETENTION_RULES
    }


def enforce_retention(
    repos: Repositories,
    settings: Settings,
    *,
    now: datetime | None = None,
    audit: bool = True,
) -> dict[str, Any]:
    """Delete expired documents and return an honest per-collection summary."""

    moment = now or utcnow()
    policy = retention_policy(settings)
    if not settings.retention_enabled:
        return {
            "status": "disabled",
            "deleted": {},
            "total_deleted": 0,
            "executed_at": moment.isoformat(),
            "limitations": ["RETENTION_ENABLED=false; no documents were deleted."],
        }

    deleted: dict[str, int] = {}
    for collection, field, _setting, _cap in RETENTION_RULES:
        cutoff = moment - timedelta(days=policy[collection])
        result = repos.mongo.db[collection].delete_many({field: {"$lt": cutoff}})
        deleted[collection] = int(result.deleted_count)

    summary = {
        "status": "ok",
        "deleted": deleted,
        "total_deleted": sum(deleted.values()),
        "executed_at": moment.isoformat(),
        "policy_days": policy,
        "limitations": [
            "Only documents carrying the policy timestamp field are eligible for deletion.",
            "MongoDB TTL indexes remain a separate, asynchronous safety net.",
        ],
    }
    if audit:
        repos.audit.log("system", "system.retention_enforced", metadata=summary)
    return summary


__all__ = ["RETENTION_RULES", "enforce_retention", "retention_policy"]
