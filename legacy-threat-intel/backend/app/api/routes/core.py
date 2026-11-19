"""Overview, events, detections, incidents and investigation endpoints."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_repos, get_services, require_api_key
from app.api.routes._common import merge, paginate_args, since_days, sort_spec, text_filter, time_filter
from app.db.repositories import Repositories
from app.investigation.assistant import InvestigationAssistant
from app.schemas import FeedbackInput, IncidentStatusUpdate
from app.utils import json_safe, parse_ts, to_iso, utcnow

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/core", tags=["core"], dependencies=[Depends(require_api_key)])


@router.get("/overview/summary")
def overview_summary(repos: Repositories = Depends(get_repos)) -> dict[str, Any]:
    active_status = {"$nin": ["closed", "resolved", "false_positive"]}
    high_risk = repos.detections.count({"risk_score": {"$gte": 65}})
    critical_alerts = repos.notifications.count({"severity": "critical", "read": {"$ne": True}})
    suspicious_ips = [
        ip for ip in repos.detections.distinct("source_ip") if ip
    ]
    recent_incidents = repos.incidents.find({}, sort_field="last_seen", limit=6)
    source_health = repos.sources.find({}, sort_field="last_checked_at", limit=20)
    return json_safe(
        {
            "generated_at": utcnow(),
            "total_security_events": repos.events.count(),
            "active_incidents": repos.incidents.count({"status": active_status}),
            "high_risk_detections": high_risk,
            "critical_alerts": critical_alerts,
            "suspicious_ip_count": len(suspicious_ips),
            "threat_category_distribution": [
                {"name": row["_id"] or "unknown", "value": row["count"]}
                for row in repos.events.aggregate(
                    [
                        {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
                        {"$sort": {"count": -1}},
                        {"$limit": 10},
                    ]
                )
            ],
            "detection_source_breakdown": [
                {"name": row["_id"] or "unknown", "value": row["count"]}
                for row in repos.detections.aggregate(
                    [
                        {"$group": {"_id": "$type", "count": {"$sum": 1}}},
                        {"$sort": {"count": -1}},
                    ]
                )
            ],
            "incident_severity_distribution": [
                {"name": row["_id"] or "unknown", "value": row["count"]}
                for row in repos.incidents.aggregate(
                    [
                        {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
                        {"$sort": {"count": -1}},
                    ]
                )
            ],
            "recent_incidents": [
                {
                    "incident_id": item.get("incident_id"),
                    "title": item.get("title"),
                    "severity": item.get("severity"),
                    "risk_score": item.get("risk_score"),
                    "status": item.get("status"),
                    "last_seen": item.get("last_seen"),
                }
                for item in recent_incidents
            ],
            "data_source_health": [
                {
                    "name": item.get("name"),
                    "status": item.get("status"),
                    "available": item.get("available"),
                    "reason": item.get("reason"),
                }
                for item in source_health
            ],
        }
    )


@router.get("/overview/events-over-time")
def events_over_time(
    days: int = Query(7, ge=1, le=365),
    repos: Repositories = Depends(get_repos),
) -> list[dict[str, Any]]:
    since = since_days(days)
    try:
        rows = repos.events.aggregate(
            [
                {"$match": {"timestamp": {"$gte": since}}},
                {
                    "$group": {
                        "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                        "count": {"$sum": 1},
                    }
                },
                {"$sort": {"_id": 1}},
            ]
        )
        return [{"date": row["_id"], "count": int(row["count"])} for row in rows]
    except Exception as exc:  # noqa: BLE001 - mongomock/older servers may lack dateToString
        logger.debug("aggregation fallback for events-over-time: %s", exc)
        events = repos.events.find({"timestamp": {"$gte": since}}, sort_field="timestamp", limit=10000)
        counts = Counter(to_iso(parse_ts(event["timestamp"]))[:10] for event in events)
        return [{"date": day, "count": count} for day, count in sorted(counts.items())]


@router.get("/events")
def list_events(
    page: int = 1,
    page_size: int = 25,
    q: str | None = None,
    event_type: str | None = None,
    source_ip: str | None = None,
    severity: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort: str | None = None,
    order: str = "desc",
    repos: Repositories = Depends(get_repos),
) -> dict[str, Any]:
    page, page_size = paginate_args(page, page_size)
    filters = [
        time_filter("timestamp", date_from, date_to),
        text_filter(q, ["message", "actor_user", "source_ip", "destination_host", "host", "event_type"]),
    ]
    if event_type:
        filters.append({"event_type": event_type})
    if source_ip:
        filters.append({"source_ip": source_ip})
    if severity:
        filters.append({"tags": {"$in": [f"severity:{severity}"]}})
    return repos.events.paginate(
        merge(*filters),
        page=page,
        page_size=page_size,
        sort_field=sort if sort in {"timestamp", "ingested_at", "event_type", "source_ip", "actor_user"} else "timestamp",
        order=1 if order.lower() == "asc" else -1,
    )


@router.get("/events/{event_id}")
def get_event(event_id: str, repos: Repositories = Depends(get_repos)) -> dict[str, Any]:
    event = repos.events.find_one({"event_id": event_id})
    if not event:
        raise HTTPException(404, "event not found")
    return json_safe(event)


@router.get("/detections")
def list_detections(
    page: int = 1,
    page_size: int = 25,
    q: str | None = None,
    detection_type: str | None = None,
    severity: str | None = None,
    min_score: float | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort: str | None = None,
    order: str = "desc",
    repos: Repositories = Depends(get_repos),
) -> dict[str, Any]:
    page, page_size = paginate_args(page, page_size)
    filters = [
        time_filter("created_at", date_from, date_to),
        text_filter(q, ["title", "description", "source_ip", "actor_user", "rule_id"]),
    ]
    if detection_type:
        filters.append({"type": detection_type})
    if severity:
        filters.append({"severity": severity})
    if min_score is not None:
        filters.append({"risk_score": {"$gte": float(min_score)}})
    return repos.detections.paginate(
        merge(*filters),
        page=page,
        page_size=page_size,
        sort_field=sort if sort in {"created_at", "risk_score", "severity", "title"} else "created_at",
        order=1 if order.lower() == "asc" else -1,
    )


@router.get("/incidents")
def list_incidents(
    page: int = 1,
    page_size: int = 25,
    q: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    severity: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort: str | None = None,
    order: str = "desc",
    repos: Repositories = Depends(get_repos),
) -> dict[str, Any]:
    page, page_size = paginate_args(page, page_size)
    filters = [
        time_filter("last_seen", date_from, date_to),
        text_filter(q, ["title", "description", "correlation_key", "incident_id"]),
    ]
    if status_filter:
        filters.append({"status": status_filter})
    if severity:
        filters.append({"severity": severity})
    return repos.incidents.paginate(
        merge(*filters),
        page=page,
        page_size=page_size,
        sort_field=sort if sort in {"last_seen", "first_seen", "risk_score", "severity"} else "last_seen",
        order=1 if order.lower() == "asc" else -1,
    )


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: str, repos: Repositories = Depends(get_repos)) -> dict[str, Any]:
    incident = repos.incidents.find_one({"incident_id": incident_id})
    if not incident:
        raise HTTPException(404, "incident not found")
    return json_safe(incident)


@router.patch("/incidents/{incident_id}/status")
def update_incident_status(
    incident_id: str,
    payload: IncidentStatusUpdate,
    repos: Repositories = Depends(get_repos),
) -> dict[str, Any]:
    incident = repos.incidents.set_status(incident_id, payload.status, payload.note)
    if not incident:
        raise HTTPException(404, "incident not found")
    repos.audit.write(
        "incident_status_changed",
        "analyst",
        {"incident_id": incident_id, "status": payload.status, "note": payload.note},
    )
    return json_safe(incident)


@router.get("/incidents/{incident_id}/investigation")
def investigate(
    incident_id: str,
    repos: Repositories = Depends(get_repos),
) -> dict[str, Any]:
    return json_safe(InvestigationAssistant(repos).build(incident_id))


@router.post("/feedback")
def add_feedback(
    payload: FeedbackInput,
    repos: Repositories = Depends(get_repos),
) -> dict[str, Any]:
    detection = repos.detections.find_one({"detection_id": payload.detection_id})
    if not detection:
        raise HTTPException(404, "detection not found")
    feedback = payload.model_dump()
    if feedback.get("label") is None:
        feedback["label"] = (
            "malicious" if payload.verdict in {"true_positive", "malicious"} else "benign"
        )
    stored = repos.feedback.add(feedback)
    repos.audit.write("analyst_feedback", payload.analyst, {"detection_id": payload.detection_id, "verdict": payload.verdict})
    return json_safe(stored)


@router.post("/run/{job_name}")
def run_job(
    job_name: str,
    services: dict[str, Any] = Depends(get_services),
) -> dict[str, Any]:
    scheduler = services.get("scheduler")
    if not scheduler:
        raise HTTPException(503, "scheduler unavailable")
    if job_name not in scheduler.JOB_INTERVALS:
        raise HTTPException(404, "unknown job")
    return scheduler.run_job(job_name)
