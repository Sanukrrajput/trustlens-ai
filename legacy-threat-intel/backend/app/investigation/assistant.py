"""Deterministic investigation explanations built strictly from stored evidence.

No LLM is required. If added later, it may summarize these facts but must not
invent events, indicators, outcomes or attacker intent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.utils import json_safe, to_iso, utcnow

if TYPE_CHECKING:
    from app.db.repositories import Repositories


class InvestigationAssistant:
    def __init__(self, repos: "Repositories"):
        self.repos = repos

    def build(self, incident_id: str) -> dict[str, Any]:
        incident = self.repos.incidents.find_one({"incident_id": incident_id})
        if not incident:
            return {"error": "incident not found", "incident_id": incident_id}

        event_ids = list(incident.get("related_event_ids") or incident.get("event_ids") or [])
        events = self.repos.events.find_by_ids(event_ids)
        detection_ids = list(incident.get("detection_ids") or [])
        detections = self.repos.detections.find(
            {"detection_id": {"$in": detection_ids}}, sort_field="risk_score", limit=200
        ) if detection_ids else []
        indicator_ids = list(incident.get("threat_indicators") or incident.get("indicators") or [])
        indicators = self.repos.indicators.find(
            {"indicator_id": {"$in": indicator_ids}}, sort_field="confidence", limit=200
        ) if indicator_ids else []
        assets = self.repos.assets.by_id()
        affected = [assets.get(str(name)) for name in incident.get("affected_assets") or [] if str(name) in assets]

        timestamps = [event.get("timestamp") for event in events if event.get("timestamp")]
        event_types = sorted({str(event.get("event_type")) for event in events})
        source_ips = sorted({str(event["source_ip"]) for event in events if event.get("source_ip")})
        users = sorted({str(event["actor_user"]) for event in events if event.get("actor_user")})
        rule_ids = sorted({str(d.get("rule_id")) for d in detections if d.get("rule_id")})
        success_after_failures = any(d.get("rule_id") == "R003" for d in detections)

        sections = [
            {
                "key": "what_happened",
                "title": "What happened",
                "content": (
                    f"{incident.get('title', 'Untitled incident')}. "
                    f"{len(detections)} detection(s) correlated from {len(events)} stored security event(s). "
                    "This is an evidence summary, not a conclusion about attacker intent."
                ),
            },
            {
                "key": "when",
                "title": "When it happened",
                "content": (
                    f"First observed {to_iso(incident.get('first_seen'))}; last observed {to_iso(incident.get('last_seen'))}. "
                    f"Event timestamps range from {to_iso(min(timestamps)) if timestamps else 'unavailable'} "
                    f"to {to_iso(max(timestamps)) if timestamps else 'unavailable'}."
                ),
            },
            {
                "key": "assets",
                "title": "Which asset was involved",
                "content": (
                    ", ".join(
                        f"{a.get('hostname') or a.get('asset_id')} (criticality {a.get('criticality')}, owner {a.get('owner') or 'unassigned'})"
                        for a in affected
                    )
                    if affected
                    else "No monitored asset was linked to the available evidence."
                ),
            },
            {
                "key": "indicators",
                "title": "Which indicators matched",
                "content": (
                    ", ".join(
                        f"{i.get('type')}:{i.get('normalized_value')} (confidence {i.get('confidence')}, source(s): "
                        f"{', '.join(str(s.get('name')) for s in i.get('sources', [])) or 'local only'})"
                        for i in indicators
                    )
                    if indicators
                    else "No threat-intelligence indicator was linked to this incident."
                ),
            },
            {
                "key": "why_suspicious",
                "title": "Why it was considered suspicious",
                "content": (
                    "; ".join(
                        reason
                        for detection in detections
                        for reason in (detection.get("detection_reasons") or [])[:4]
                    )
                    or "The underlying detection reasons are not available in stored records."
                )
                + (f" Triggered rule/model identifiers: {', '.join(rule_ids)}." if rule_ids else ""),
            },
            {
                "key": "connected_events",
                "title": "Which events are connected",
                "content": (
                    f"{len(events)} event(s) of type {', '.join(event_types) or 'unknown'} from source IP(s) "
                    f"{', '.join(source_ips) or 'unavailable'} and account(s) {', '.join(users) or 'unavailable'} "
                    "are referenced by this incident."
                ),
            },
            {
                "key": "evidence",
                "title": "What evidence supports the detection",
                "content": (
                    "; ".join(
                        f"{d.get('title')} (score {d.get('risk_score')}, confidence {d.get('confidence')}, "
                        f"events {len(d.get('event_ids') or [])})"
                        for d in detections
                    )
                    or "No detection records are attached; verify the incident correlation data."
                ),
            },
            {
                "key": "outcome",
                "title": "Outcome assessment",
                "content": (
                    "A successful authentication after repeated failures was recorded; verify it with the account owner. "
                    "Stored evidence does not by itself prove that a compromise occurred."
                    if success_after_failures
                    else "Stored evidence does not establish that any attack succeeded. No destructive action has been taken."
                ),
            },
            {
                "key": "next_steps",
                "title": "What to investigate next",
                "content": " ".join(incident.get("recommended_steps") or ["Review the referenced events before deciding on a response."]),
            },
        ]
        return {
            "incident_id": incident_id,
            "generated_at": utcnow(),
            "sections": sections,
            "evidence_counts": {
                "events": len(events),
                "detections": len(detections),
                "indicators": len(indicators),
                "assets": len(affected),
            },
            "event_references": [json_safe(event.get("event_id")) for event in events[:100]],
            "disclaimer": "Generated from database evidence only. Analyst verification is required.",
        }
