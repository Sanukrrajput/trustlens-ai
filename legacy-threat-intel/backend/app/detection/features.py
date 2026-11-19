"""Feature engineering shared by ML training and inference (no label leakage)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

FEATURE_NAMES: list[str] = [
    "failed_login_count",
    "successful_login_count",
    "events_per_window",
    "unique_destination_count",
    "login_time_deviation",
    "request_frequency",
    "asset_criticality",
    "ti_confidence",
    "is_auth_event",
    "is_api_event",
    "is_network_event",
    "is_powershell_event",
    "is_admin_event",
    "protocol_known",
]

AUTH_TYPES = {"auth_failure", "auth_success", "auth_logout"}
API_TYPES = {"api_request", "api_rate_limit", "api_error"}
NETWORK_TYPES = {"network_connection", "firewall", "dns", "ids_alert", "ti_feed"}
POWERSHELL_TYPES = {"powershell_script", "powershell"}
ADMIN_TYPES = {"privilege_assigned", "account_change", "service_installed", "audit_cleared"}


def lookup_indicator(indicators_map: dict[str, dict], kind: str, value: str) -> dict | None:
    """Resolve an event indicator against the local intelligence map."""
    keys = [f"{kind}:{value}"]
    if kind in {"ip", "ipv4", "ipv6"}:
        keys.extend([f"ip:{value}", f"ipv4:{value}", f"ipv6:{value}"])
    for key in keys:
        match = indicators_map.get(key)
        if match:
            return match
    return None


def entity_key(event: dict[str, Any]) -> str:
    for field in ("actor_user", "source_ip", "asset_id", "host"):
        value = event.get(field)
        if value:
            return f"{field}:{value}"
    return "unknown"


def window_start(timestamp: datetime, minutes: int = 15) -> datetime:
    timestamp = timestamp.astimezone(timezone.utc) if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)
    floored = timestamp.replace(second=0, microsecond=0)
    return floored.replace(minute=(floored.minute // minutes) * minutes)


def _login_deviation(timestamp: datetime, business_start: int = 8, business_end: int = 18) -> float:
    hour = timestamp.astimezone(timezone.utc).hour if timestamp.tzinfo else timestamp.hour
    if business_start <= hour < business_end:
        return 0.0
    if hour >= business_end:
        return float(hour - business_end)
    return float(business_start - hour)


def build_feature_vectors(
    events: Iterable[dict[str, Any]],
    indicators_map: dict[str, dict] | None = None,
    *,
    window_minutes: int = 15,
    business_start: int = 8,
    business_end: int = 18,
) -> list[dict[str, Any]]:
    """Aggregate events into entity/time-window vectors with stable feature order."""
    indicators_map = indicators_map or {}
    groups: dict[tuple[str, datetime], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        timestamp = event.get("timestamp")
        if timestamp is None:
            continue
        from app.utils import parse_ts

        groups[(entity_key(event), window_start(parse_ts(timestamp), window_minutes))].append(event)

    vectors: list[dict[str, Any]] = []
    for (entity, start), group in groups.items():
        destinations: set[str] = set()
        asset_criticality = 0
        ti_confidence = 0.0
        deviations: list[float] = []
        failed = success = api_calls = 0
        auth = api = network = powershell = admin = False
        protocols: set[str] = set()
        event_ids: list[str] = []
        for event in group:
            event_type = str(event.get("event_type") or "")
            if event_type in AUTH_TYPES or "auth_failure" in event_type or "auth_success" in event_type:
                auth = True
            if event_type in API_TYPES or "api" in event_type:
                api = True
                api_calls += 1
            if event_type in NETWORK_TYPES:
                network = True
            if event_type in POWERSHELL_TYPES:
                powershell = True
            if event_type in ADMIN_TYPES:
                admin = True
            if "failure" in event_type or "failed" in event_type:
                failed += 1
            if "success" in event_type:
                success += 1
            for key in ("destination_ip", "destination_host", "source_ip"):
                if event.get(key):
                    destinations.add(str(event[key]))
            asset_criticality = max(asset_criticality, int(event.get("asset_criticality") or 0))
            if event.get("protocol"):
                protocols.add(str(event["protocol"]).lower())
            if "auth" in event_type:
                from app.utils import parse_ts

                deviations.append(_login_deviation(parse_ts(event["timestamp"]), business_start, business_end))
            for indicator in event.get("indicators") or []:
                value = indicator.get("value") if isinstance(indicator, dict) else str(indicator)
                kind = indicator.get("type") if isinstance(indicator, dict) else "ip"
                match = lookup_indicator(indicators_map, str(kind), str(value))
                if match:
                    ti_confidence = max(ti_confidence, float(match.get("confidence") or 0))
            event_ids.append(str(event.get("event_id") or ""))

        features = {
            "failed_login_count": float(failed),
            "successful_login_count": float(success),
            "events_per_window": float(len(group)),
            "unique_destination_count": float(len(destinations)),
            "login_time_deviation": float(sum(deviations) / len(deviations)) if deviations else 0.0,
            "request_frequency": float(api_calls) / max(1.0, window_minutes / 60.0),
            "asset_criticality": float(asset_criticality),
            "ti_confidence": ti_confidence,
            "is_auth_event": float(auth),
            "is_api_event": float(api),
            "is_network_event": float(network),
            "is_powershell_event": float(powershell),
            "is_admin_event": float(admin),
            "protocol_known": float(bool(protocols)),
        }
        vectors.append(
            {
                "entity_key": entity,
                "window_start": start,
                "window_end": start + timedelta(minutes=window_minutes),
                "features": {name: float(features[name]) for name in FEATURE_NAMES},
                "event_ids": [eid for eid in event_ids if eid],
                "source_ip": next((str(e.get("source_ip")) for e in group if e.get("source_ip")), None),
                "actor_user": next((str(e.get("actor_user")) for e in group if e.get("actor_user")), None),
                "asset_ids": [str(e["asset_id"]) for e in group if e.get("asset_id")],
            }
        )
    return vectors
