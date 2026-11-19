"""Groups related detections into deduplicated, evidence-backed incidents."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from app.utils import make_id, parse_ts, utcnow

if TYPE_CHECKING:
    from app.config import Settings
    from app.db.repositories import Repositories

logger = logging.getLogger(__name__)
SEVERITY_RANK = {"informational": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def recommended_steps(detections: list[dict[str, Any]]) -> list[str]:
    rules = {str(d.get("rule_id") or "") for d in detections}
    steps: list[str] = []
    if rules & {"R001", "R002", "R003", "R010"}:
        steps.append("Review the full authentication trail for the affected accounts and source IP in the identity provider.")
        steps.append("Confirm with the account owner whether the successful logon was expected; avoid account changes until approved.")
    if rules & {"R005", "R006"}:
        steps.append("Verify matched indicators against a second intelligence source before taking any containment action.")
    if rules & {"R008", "R009"}:
        steps.append("Inspect privileged activity and change records on the affected asset for unauthorized modifications.")
    if any(d.get("type") == "ml" for d in detections):
        steps.append("Treat anomaly scores as leads only; inspect the underlying events before drawing conclusions.")
    steps.append("Preserve the referenced events and raw logs according to your retention policy.")
    return list(dict.fromkeys(steps))[:10]


class IncidentCorrelator:
    def __init__(self, settings: "Settings", repos: "Repositories"):
        self.settings = settings
        self.repos = repos

    def _fingerprint(self, detection: dict[str, Any]) -> tuple[str, str]:
        window_hours = max(1, int(self.settings.correlation_window_hours))
        timestamp = parse_ts(detection.get("window_start") or detection.get("created_at") or utcnow())
        bucket = timestamp.replace(minute=0, second=0, microsecond=0)
        bucket = bucket.replace(hour=(bucket.hour // window_hours) * window_hours)
        key = (
            detection.get("source_ip")
            or detection.get("actor_user")
            or (detection.get("asset_ids") or [None])[0]
            or detection.get("entity_key")
            or "unknown"
        )
        return str(key), make_id("inc", str(key), bucket.isoformat())

    def correlate(self, detections: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if detections is None:
            detections = self.repos.detections.find(
                {"incident_id": {"$exists": False}}, sort_field="created_at", limit=500
            )
        if not detections:
            return {"incidents_created": 0, "incidents_updated": 0, "detections_correlated": 0}

        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        keys: dict[str, str] = {}
        for detection in detections:
            key, fingerprint = self._fingerprint(detection)
            groups[fingerprint].append(detection)
            keys[fingerprint] = key

        created = updated = 0
        for fingerprint, group in groups.items():
            existing = self.repos.incidents.find_active_by_fingerprint(fingerprint)
            timestamps = [
                parse_ts(d.get("window_start") or d.get("created_at") or utcnow()) for d in group
            ]
            first_seen = min(timestamps)
            last_seen = max(
                [parse_ts(d.get("last_seen") or d.get("created_at") or utcnow()) for d in group]
                + ([parse_ts(existing["last_seen"])] if existing and existing.get("last_seen") else [])
            )
            severity = max(
                (d.get("severity") or "informational" for d in group),
                key=lambda value: SEVERITY_RANK.get(str(value), 0),
            )
            risk_score = max(float(d.get("risk_score") or 0) for d in group)
            event_ids = list(dict.fromkeys(eid for d in group for eid in d.get("event_ids", [])))
            detection_ids = list(dict.fromkeys(str(d["detection_id"]) for d in group if d.get("detection_id")))
            indicators = list(dict.fromkeys(iid for d in group for iid in d.get("indicator_ids", [])))
            assets = list(dict.fromkeys(aid for d in group for aid in d.get("asset_ids", [])))
            key = keys[fingerprint]
            timeline = [
                {
                    "at": d.get("created_at") or d.get("window_start"),
                    "event": "detection_correlated",
                    "detection_id": d.get("detection_id"),
                    "title": d.get("title"),
                    "risk_score": d.get("risk_score"),
                }
                for d in group
            ]
            incident = {
                "fingerprint": fingerprint,
                "correlation_key": key,
                "title": f"{str(severity).title()} security incident involving {key}",
                "description": (
                    f"{len(group)} correlated detection(s) and {len(event_ids)} referenced event(s) "
                    f"were observed for {key} between {first_seen.isoformat()} and {last_seen.isoformat()}. "
                    "Findings are based on stored evidence and require analyst verification."
                ),
                "severity": str(severity),
                "risk_score": round(risk_score, 2),
                "status": "new" if not existing else existing.get("status", "new"),
                "related_event_ids": event_ids,
                "event_ids": event_ids,
                "detection_ids": detection_ids,
                "indicators": indicators,
                "threat_indicators": indicators,
                "affected_assets": assets,
                "first_seen": first_seen,
                "last_seen": last_seen,
                "evidence": [
                    {"detection_id": d.get("detection_id"), "title": d.get("title"), "reasons": d.get("detection_reasons", [])}
                    for d in group
                ],
                "timeline": timeline,
                "recommended_steps": recommended_steps(group),
                "updated_at": utcnow(),
                "expires_at": utcnow() + timedelta(days=self.settings.incident_retention_days),
            }
            stored = self.repos.incidents.upsert(incident)
            incident_id = stored.get("incident_id")
            if existing:
                updated += 1
            else:
                created += 1
            for detection in group:
                self.repos.detections.update_one(
                    {"detection_id": detection["detection_id"]}, {"$set": {"incident_id": incident_id}}
                )
        logger.info("correlation created=%s updated=%s detections=%s", created, updated, len(detections))
        return {
            "incidents_created": created,
            "incidents_updated": updated,
            "detections_correlated": len(detections),
        }
