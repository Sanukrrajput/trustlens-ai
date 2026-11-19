"""Configurable, evidence-based detection rules.

Rules deliberately avoid treating a single failed login or a shared public IP as
proof of an attack. Every candidate records the evidence used.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from app.detection.features import ADMIN_TYPES, build_feature_vectors, lookup_indicator, window_start
from app.utils import make_id, parse_ts

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger(__name__)
RULE_VERSION = "1.0.0"

SEVERITY_SCORE = {
    "informational": 10,
    "low": 25,
    "medium": 45,
    "high": 70,
    "critical": 90,
}


class RuleEngine:
    def __init__(self, settings: "Settings", thresholds: dict[str, Any] | None = None):
        self.settings = settings
        self.thresholds = thresholds or {}

    def value(self, name: str, default: Any) -> Any:
        return self.thresholds.get(name, getattr(self.settings, name, default))

    def evaluate(self, events: list[dict[str, Any]], indicators_map: dict[str, dict]) -> list[dict[str, Any]]:
        if not events:
            return []
        vectors = build_feature_vectors(
            events,
            indicators_map,
            window_minutes=15,
            business_start=int(self.value("rule_unusual_hours_start", 22)),
            business_end=int(self.value("rule_unusual_hours_end", 6)),
        )
        by_id = {str(event.get("event_id")): event for event in events}
        candidates: list[dict[str, Any]] = []
        for vector in vectors:
            group = [by_id[eid] for eid in vector["event_ids"] if eid in by_id]
            candidates.extend(self._per_group_rules(vector, group, indicators_map))
        candidates.extend(self._cross_event_rules(events, indicators_map))
        return candidates

    def _candidate(
        self,
        *,
        rule_id: str,
        title: str,
        severity: str,
        reasons: list[str],
        signals: dict[str, Any],
        group: list[dict[str, Any]],
        indicators_map: dict[str, dict],
        confidence: float = 0.7,
        entity_key: str = "",
        window_start_value: Any = None,
    ) -> dict[str, Any]:
        ti_confidence = 0.0
        indicator_ids: list[str] = []
        for event in group:
            for indicator in event.get("indicators") or []:
                value = indicator.get("value") if isinstance(indicator, dict) else str(indicator)
                kind = indicator.get("type") if isinstance(indicator, dict) else "ip"
                match = lookup_indicator(indicators_map, str(kind), str(value))
                if match:
                    ti_confidence = max(ti_confidence, float(match.get("confidence") or 0))
                    indicator_ids.append(str(match.get("indicator_id") or ""))
        event_ids = [str(event.get("event_id") or "") for event in group]
        source_ip = next((str(e["source_ip"]) for e in group if e.get("source_ip")), None)
        actor_user = next((str(e["actor_user"]) for e in group if e.get("actor_user")), None)
        asset_ids = [str(e["asset_id"]) for e in group if e.get("asset_id")]
        criticality = max((int(e.get("asset_criticality") or 0) for e in group), default=0)
        start = window_start_value or (parse_ts(group[0]["timestamp"]) if group and group[0].get("timestamp") else None)
        entity = entity_key or (actor_user or source_ip or "unknown")
        return {
            "type": "rule",
            "rule_id": rule_id,
            "title": title,
            "severity": severity,
            "base_score": SEVERITY_SCORE[severity],
            "confidence": min(0.99, max(0.1, confidence)),
            "reasons": reasons,
            "signals": signals,
            "event_ids": list(dict.fromkeys(eid for eid in event_ids if eid)),
            "entity_key": entity,
            "source_ip": source_ip,
            "actor_user": actor_user,
            "asset_ids": list(dict.fromkeys(asset_ids)),
            "indicator_ids": list(dict.fromkeys(iid for iid in indicator_ids if iid)),
            "ti_confidence": ti_confidence,
            "asset_criticality": criticality,
            "correlation_evidence": min(1.0, 0.2 * len(group) + 0.2 * len(set(asset_ids))),
            "window_start": start,
            "rule_version": RULE_VERSION,
            "detection_key": make_id("det", rule_id, entity, start.isoformat() if start else "na"),
        }

    def _per_group_rules(
        self,
        vector: dict[str, Any],
        group: list[dict[str, Any]],
        indicators_map: dict[str, dict],
    ) -> list[dict[str, Any]]:
        if not group:
            return []
        features = vector["features"]
        results: list[dict[str, Any]] = []
        failed_threshold = int(self.value("rule_failed_login_threshold", 5))
        failed = int(features["failed_login_count"])

        if failed >= max(2, failed_threshold):
            severity = "high" if failed >= failed_threshold * 2 else "medium"
            results.append(
                self._candidate(
                    rule_id="R001",
                    title="Repeated failed logins",
                    severity=severity,
                    reasons=[
                        f"{failed} failed authentication events in a 15-minute window",
                        "threshold requires multiple failures before alerting",
                    ],
                    signals={
                        "failed_login_count": failed,
                        "window_minutes": 15,
                        "threshold": failed_threshold,
                    },
                    group=group,
                    indicators_map=indicators_map,
                    confidence=min(0.95, 0.6 + failed / (failed_threshold * 4)),
                    entity_key=vector["entity_key"],
                    window_start_value=vector["window_start"],
                )
            )

        api_threshold = float(self.value("rule_api_rate_threshold", 120))
        if features["request_frequency"] >= api_threshold:
            results.append(
                self._candidate(
                    rule_id="R007",
                    title="Abnormal API request frequency",
                    severity="medium",
                    reasons=[f"estimated request rate {features['request_frequency']:.1f}/hour exceeds configured baseline"],
                    signals={"request_frequency": features["request_frequency"], "threshold": api_threshold},
                    group=group,
                    indicators_map=indicators_map,
                    confidence=0.7,
                    entity_key=vector["entity_key"],
                    window_start_value=vector["window_start"],
                )
            )

        unusual_deviation = float(features["login_time_deviation"])
        if features["successful_login_count"] >= 1 and unusual_deviation >= 2 and len(group) >= 2:
            results.append(
                self._candidate(
                    rule_id="R004",
                    title="Unusual login time",
                    severity="low",
                    reasons=[
                        f"successful authentication {unusual_deviation:.1f}h outside configured business hours",
                        "corroborated by additional activity in the same window",
                    ],
                    signals={"login_time_deviation_hours": unusual_deviation},
                    group=group,
                    indicators_map=indicators_map,
                    confidence=0.55,
                    entity_key=vector["entity_key"],
                    window_start_value=vector["window_start"],
                )
            )

        malicious_confidence = float(self.value("rule_malicious_confidence", 0.65))
        ip_events = [
            event
            for event in group
            if any(
                (match := lookup_indicator(indicators_map, "ip", str(indicator.get("value"))))
                and float(match.get("confidence") or 0) >= malicious_confidence
                for indicator in (event.get("indicators") or [])
                if isinstance(indicator, dict) and indicator.get("type") == "ip"
            )
        ]
        if ip_events:
            results.append(
                self._candidate(
                    rule_id="R005",
                    title="Known malicious IP address observed",
                    severity="high",
                    reasons=["event source/destination matches a local threat-intelligence indicator above the confidence threshold"],
                    signals={"matched_ip_events": len(ip_events), "confidence_threshold": malicious_confidence},
                    group=ip_events,
                    indicators_map=indicators_map,
                    confidence=0.85,
                    entity_key=vector["entity_key"],
                    window_start_value=vector["window_start"],
                )
            )

        domain_events = [
            event
            for event in group
            if any(
                (match := lookup_indicator(indicators_map, str(indicator.get("type")), str(indicator.get("value"))))
                and match.get("is_malicious")
                and float(match.get("confidence") or 0) >= malicious_confidence
                for indicator in (event.get("indicators") or [])
                if isinstance(indicator, dict) and indicator.get("type") in {"domain", "url"}
            )
        ]
        if domain_events:
            results.append(
                self._candidate(
                    rule_id="R006",
                    title="Suspicious domain or URL observed",
                    severity="medium",
                    reasons=["event references a domain/URL flagged by configured threat-intelligence evidence"],
                    signals={"matched_events": len(domain_events)},
                    group=domain_events,
                    indicators_map=indicators_map,
                    confidence=0.78,
                    entity_key=vector["entity_key"],
                    window_start_value=vector["window_start"],
                )
            )

        criticality_threshold = int(self.value("critical_asset_criticality", 4))
        high_value = int(features["asset_criticality"]) >= criticality_threshold
        sensitive_events = [
            event
            for event in group
            if event.get("event_type") in ADMIN_TYPES
            or "failure" in str(event.get("event_type"))
            or event.get("event_type") == "audit_cleared"
        ]
        if high_value and sensitive_events:
            results.append(
                self._candidate(
                    rule_id="R009",
                    title="Sensitive activity on critical asset",
                    severity="high",
                    reasons=[
                        f"asset criticality {int(features['asset_criticality'])} meets configured critical threshold",
                        "authentication failure or administrative activity observed on the asset",
                    ],
                    signals={"asset_criticality": int(features["asset_criticality"]), "sensitive_events": len(sensitive_events)},
                    group=sensitive_events,
                    indicators_map=indicators_map,
                    confidence=0.75,
                    entity_key=vector["entity_key"],
                    window_start_value=vector["window_start"],
                )
            )
        return results

    def _cross_event_rules(
        self, events: list[dict[str, Any]], indicators_map: dict[str, dict]
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        by_ip: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for event in events:
            if event.get("source_ip"):
                by_ip[str(event["source_ip"])].append(event)

        brute_threshold = int(self.value("rule_brute_force_threshold", 10))
        account_threshold = int(self.value("rule_brute_force_accounts", 3))
        multi_threshold = max(2, account_threshold)
        success_threshold = int(self.value("rule_success_after_failures", 3))
        success_window = timedelta(minutes=int(self.value("rule_success_after_failures_window_minutes", 30)))

        for source_ip, ip_events in by_ip.items():
            failures = [e for e in ip_events if "failure" in str(e.get("event_type"))]
            failure_users = {str(e.get("actor_user") or "unknown") for e in failures}
            start = min((parse_ts(e["timestamp"]) for e in ip_events), default=None)
            end = max((parse_ts(e["timestamp"]) for e in ip_events), default=None)
            if len(failures) >= brute_threshold and len(failure_users) >= account_threshold:
                results.append(
                    self._candidate(
                        rule_id="R002",
                        title="Brute-force authentication pattern",
                        severity="high",
                        reasons=[
                            f"{len(failures)} failed logons across {len(failure_users)} accounts from one source",
                            "pattern is inconsistent with normal single-user authentication",
                        ],
                        signals={"failed_logons": len(failures), "distinct_accounts": len(failure_users)},
                        group=failures,
                        indicators_map=indicators_map,
                        confidence=0.88,
                        entity_key=f"ip:{source_ip}",
                        window_start_value=window_start(start) if start else None,
                    )
                )
            elif len(failure_users) >= multi_threshold and len(failures) >= 2:
                results.append(
                    self._candidate(
                        rule_id="R010",
                        title="Failures across multiple accounts",
                        severity="low",
                        reasons=[f"{len(failures)} failures spanning {len(failure_users)} accounts from one source"],
                        signals={"failed_logons": len(failures), "distinct_accounts": len(failure_users)},
                        group=failures,
                        indicators_map=indicators_map,
                        confidence=0.55,
                        entity_key=f"ip:{source_ip}",
                        window_start_value=window_start(start) if start else None,
                    )
                )

            sorted_ip_events = sorted(ip_events, key=lambda e: parse_ts(e["timestamp"]))
            for index, event in enumerate(sorted_ip_events):
                if "success" not in str(event.get("event_type")):
                    continue
                event_time = parse_ts(event["timestamp"])
                preceding = [
                    e
                    for e in sorted_ip_events[:index]
                    if "failure" in str(e.get("event_type"))
                    and 0 <= (event_time - parse_ts(e["timestamp"])).total_seconds() <= success_window.total_seconds()
                ]
                if len(preceding) >= success_threshold:
                    results.append(
                        self._candidate(
                            rule_id="R003",
                            title="Successful login after repeated failures",
                            severity="high",
                            reasons=[
                                f"successful authentication followed {len(preceding)} failures from the same source within {int(success_window.total_seconds() / 60)} minutes",
                                "potential credential guessing followed by a valid authentication",
                            ],
                            signals={"preceding_failures": len(preceding), "window_minutes": int(success_window.total_seconds() / 60)},
                            group=preceding + [event],
                            indicators_map=indicators_map,
                            confidence=0.82,
                            entity_key=f"ip:{source_ip}",
                            window_start_value=window_start(event_time),
                        )
                    )

            admin_events = [e for e in ip_events if e.get("event_type") in ADMIN_TYPES]
            if admin_events and failures:
                results.append(
                    self._candidate(
                        rule_id="R008",
                        title="Administrative activity from an IP with authentication failures",
                        severity="medium",
                        reasons=[
                            "privileged or account-change event originated from a source that also produced authentication failures",
                            "correlation required; administrative event alone is not treated as malicious",
                        ],
                        signals={"admin_events": len(admin_events), "failed_logons": len(failures)},
                        group=admin_events + failures[:10],
                        indicators_map=indicators_map,
                        confidence=0.65,
                        entity_key=f"ip:{source_ip}",
                        window_start_value=window_start(min((parse_ts(e["timestamp"]) for e in admin_events), default=end)),
                    )
                )
        return results
