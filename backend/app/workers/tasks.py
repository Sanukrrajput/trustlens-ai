"""Background tasks: monitoring, intelligence refresh, analytics and health."""

from __future__ import annotations

import hashlib
import logging
from datetime import timedelta
from typing import Any

import requests

from app.core.security import utcnow
from app.workers.celery_app import celery_app
from app.workers.context import worker_context

logger = logging.getLogger(__name__)


def _status(task_id: str, status: str, **extra: Any) -> None:
    ctx = worker_context()
    ctx["repos"].tasks.set(task_id, status, **extra)


@celery_app.task(bind=True, autoretry_for=(requests.RequestException,), retry_backoff=True)
def run_analysis_task(self, analysis_kind: str, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    task_id = str(self.request.id)
    _status(task_id, "started", kind="analysis")
    try:
        from app.services.analysis_service import AnalysisService

        ctx = worker_context()
        service = AnalysisService(ctx["settings"], ctx["repos"], ctx["notifications"], ctx["plans"])
        result = service.run(user_id, analysis_kind, payload)
        _status(task_id, "completed", result={"analysis_id": result.get("id")})
        return {"analysis_id": result.get("id")}
    except Exception as exc:  # noqa: BLE001
        _status(task_id, "failed", error=str(exc))
        raise


def _normalise_listing(raw: dict[str, Any], source: str) -> dict[str, Any] | None:
    title = str(raw.get("title") or raw.get("job_title") or "").strip()
    company = str(raw.get("company") or raw.get("company_name") or "").strip()
    description = str(raw.get("description") or raw.get("content") or "").strip()
    if not title or not description:
        return None
    url = str(raw.get("url") or raw.get("absolute_url") or raw.get("apply_url") or "").strip()
    fingerprint_source = f"{source.lower()}|{company.lower()}|{title.lower()}|{description[:300].lower()}"
    return {
        "title": title,
        "company": company,
        "description": description,
        "url": url,
        "source": source,
        "location": str(raw.get("location") or raw.get("location_name") or ""),
        "published_at": raw.get("published_at") or raw.get("updated_at") or utcnow(),
        "fingerprint": hashlib.sha256(fingerprint_source.encode()).hexdigest(),
        "collected_at": utcnow(),
    }


def _fetch_approved_sources(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    settings = ctx["settings"]
    listings: list[dict[str, Any]] = []
    for index, source_url in enumerate(settings.job_source_urls[:20]):
        headers = {"Accept": "application/json"}
        keys = settings.job_source_api_keys
        if index < len(keys) and keys[index]:
            headers["Authorization"] = f"Bearer {keys[index]}"
        try:
            response = requests.get(source_url, headers=headers, timeout=12)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("approved job source failed url=%s error=%s", source_url, exc)
            continue
        rows = data if isinstance(data, list) else data.get("jobs") or data.get("results") or []
        for raw in rows[: settings.job_source_max_per_run]:
            if isinstance(raw, dict):
                listing = _normalise_listing(raw, source_url)
                if listing:
                    listings.append(listing)
    return listings


@celery_app.task(bind=True, autoretry_for=(requests.RequestException,), retry_backoff=True)
def run_monitoring(self) -> dict[str, Any]:
    task_id = str(self.request.id)
    _status(task_id, "started", kind="monitoring")
    ctx = worker_context()
    settings = ctx["settings"]
    if not settings.scheduler_enabled:
        _status(task_id, "skipped", reason="scheduler disabled")
        return {"status": "skipped", "reason": "scheduler disabled"}
    if not settings.job_source_urls:
        _status(task_id, "skipped", reason="no approved job sources configured")
        return {"status": "skipped", "reason": "no approved job sources configured"}

    repos = ctx["repos"]
    listings = _fetch_approved_sources(ctx)
    inserted = 0
    alerts = 0
    for listing in listings:
        result = repos.job_listings.col.update_one(
            {"fingerprint": listing["fingerprint"]}, {"$setOnInsert": listing}, upsert=True
        )
        if getattr(result, "upserted_id", None) is None:
            continue
        inserted += 1
        for task in repos.monitoring.all_enabled():
            haystack = " ".join(
                [listing.get("title", ""), listing.get("company", ""), listing.get("description", "")]
            ).lower()
            terms = [term.lower() for term in task.get("company_names", []) + task.get("job_titles", []) + task.get("keywords", []) if term]
            if terms and not any(term in haystack for term in terms):
                continue
            user = repos.users.get(str(task.get("user_id")))
            if not user:
                continue
            ctx["notifications"].monitoring_notification(
                str(user["_id"]),
                str(user.get("email") or ""),
                task_name=str(task.get("name", "monitor")),
                company=listing.get("company") or "an unlisted company",
                title=listing.get("title", "new listing"),
            )
            alerts += 1
    repos.monitoring.col.update_many({"enabled": True}, {"$set": {"last_run_at": utcnow(), "last_status": "ok"}})
    _status(task_id, "completed", result={"listings": inserted, "alerts": alerts})
    return {"status": "ok", "listings_inserted": inserted, "alerts": alerts}


@celery_app.task(bind=True)
def refresh_domain_intelligence(self) -> dict[str, Any]:
    task_id = str(self.request.id)
    _status(task_id, "started", kind="domain_refresh")
    ctx = worker_context()
    from app.intelligence.domain_analysis.analyser import DomainAnalyser

    analyser = DomainAnalyser(ctx["settings"], ctx["repos"])
    domains = list(ctx["repos"].domains.find({}, limit=200))
    refreshed = 0
    for doc in domains:
        domain = doc.get("domain")
        if domain:
            try:
                analyser.analyse(domain, refresh=True)
                refreshed += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("domain refresh failed domain=%s error=%s", domain, exc)
    _status(task_id, "completed", result={"refreshed": refreshed})
    return {"status": "ok", "refreshed": refreshed}


@celery_app.task(bind=True)
def aggregate_analytics(self) -> dict[str, Any]:
    task_id = str(self.request.id)
    _status(task_id, "started", kind="analytics")
    ctx = worker_context()
    stats = ctx["repos"].analyses.global_stats()
    patterns = ctx["repos"].analyses.pattern_counts()
    ctx["repos"].mongo.db["platform_settings"].update_one(
        {"key": "analytics_snapshot"},
        {
            "$set": {
                "key": "analytics_snapshot",
                "value": {"stats": stats, "patterns": patterns},
                "updated_at": utcnow(),
            }
        },
        upsert=True,
    )
    _status(task_id, "completed", result=stats)
    return {"status": "ok", **stats}


@celery_app.task(bind=True)
def health_check(self) -> dict[str, Any]:
    task_id = str(self.request.id)
    ctx = worker_context()
    health = ctx["mongo"].health()
    ctx["repos"].mongo.db["health_checks"].insert_one({"health": health, "created_at": utcnow()})
    _status(task_id, "completed", result=health)
    return health
