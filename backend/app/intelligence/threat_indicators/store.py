"""Threat-indicator store with a source registry and honest availability states.

The store never invents indicators. Public feeds are optional, operator-registered
JSON endpoints fetched through the SSRF-safe fetcher. When no feed is configured
or no indicator matches exist, the result is explicitly ``not_configured`` or
``not_attempted`` — never a clean bill of health.
"""

from __future__ import annotations

import ipaddress
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from urllib.parse import urlsplit

from app.intelligence import EVIDENCE_STATUSES, clamp, dedupe, iso, make_indicator, normalise_company_name
from app.intelligence.url_scanning.safe_fetch import SafeURLFetcher

INDICATOR_KINDS = ("domain", "url", "email", "phone", "brand", "ip", "fingerprint", "generic")
DEFAULT_TTL_DAYS = 90

BUILTIN_SOURCES: tuple[dict[str, Any], ...] = (
    {
        "source_id": "operator_import",
        "name": "Operator JSON import",
        "kind": "import",
        "url": None,
        "enabled": True,
        "trusted": True,
        "description": "Structured indicators supplied directly by an administrator. No network fetch is performed.",
    },
)


def normalise_indicator_value(kind: str, value: Any) -> str:
    """Normalise an indicator value so equivalent observations dedupe safely."""
    text = str(value or "").strip()
    if not text:
        return ""
    text = text[:512]
    kind = str(kind or "generic").strip().lower()
    if kind == "domain":
        host = text
        if "://" in host:
            host = urlsplit(host).hostname or ""
        host = host.split("@", 1)[-1].split(":", 1)[0].lower().rstrip(".")
        while host.startswith("www."):
            host = host[4:]
        return re.sub(r"[^a-z0-9.-]", "", host)
    if kind == "url":
        parts = urlsplit(text)
        host = (parts.hostname or "").lower().rstrip(".")
        path = re.sub(r"/+", "/", parts.path or "").rstrip("/")
        return f"{parts.scheme.lower()}://{host}{path}" if host and parts.scheme else ""
    if kind == "email":
        return text.lower().strip("<>")
    if kind == "phone":
        return re.sub(r"\D", "", text)
    if kind == "brand":
        return normalise_company_name(text)
    if kind == "ip":
        try:
            return str(ipaddress.ip_address(text))
        except ValueError:
            return ""
    if kind == "fingerprint":
        return re.sub(r"\s+", "", text.lower())
    return re.sub(r"\s+", " ", text.lower()).strip()


class ThreatIndicatorStore:
    """Own source registration, ingestion, expiry and matching."""

    def __init__(self, settings: Any, repos: Any) -> None:
        self.settings = settings
        self.repos = repos
        self.fetcher = SafeURLFetcher(settings)

    @staticmethod
    def _source_documents(repos: Any) -> list[dict[str, Any]]:
        source_repo = getattr(repos, "threat_sources", None)
        if source_repo is None:
            return []
        try:
            return source_repo.find({}, limit=100)
        except Exception:
            return []

    @staticmethod
    def _public_source(source: dict[str, Any]) -> dict[str, Any]:
        data = {
            key: source.get(key)
            for key in ("source_id", "name", "kind", "url", "enabled", "trusted", "description", "updated_at")
            if key in source
        }
        if not data.get("enabled"):
            data["status"] = "disabled"
        elif data.get("kind") == "import":
            data["status"] = "configured"
        elif data.get("url"):
            data["status"] = "configured"
        else:
            data["status"] = "not_configured"
        return data

    def sources(self) -> list[dict[str, Any]]:
        stored = {str(item.get("source_id")): item for item in self._source_documents(self.repos)}
        merged: dict[str, dict[str, Any]] = {}
        for source in BUILTIN_SOURCES:
            merged[source["source_id"]] = dict(source)
        for source_id, source in stored.items():
            merged[source_id] = {**merged.get(source_id, {}), **source}
        return [self._public_source(item) for item in merged.values()]

    def register_source(
        self,
        *,
        source_id: str,
        name: str,
        kind: str = "public_json_feed",
        url: str | None = None,
        enabled: bool = True,
        description: str = "",
    ) -> dict[str, Any]:
        source_id = re.sub(r"[^a-z0-9_-]+", "-", source_id.lower().strip()).strip("-")[:80]
        if not source_id or len(name.strip()) < 2:
            raise ValueError("a valid source_id and name are required")
        if kind not in {"public_json_feed", "import"}:
            raise ValueError("unsupported source kind")
        if url:
            # Validate structure now; DNS and the live fetch are validated again
            # at refresh time by the SSRF-safe fetcher.
            self.fetcher._validate_url(url)
        document = {
            "source_id": source_id,
            "name": name.strip()[:120],
            "kind": kind,
            "url": str(url or "").strip() or None,
            "enabled": bool(enabled),
            "trusted": False,
            "description": description.strip()[:500],
            "created_at": iso(),
        }
        repo = getattr(self.repos, "threat_sources", None)
        if repo is None:
            return self._public_source(document)
        return self._public_source(repo.upsert(source_id, document))

    def refresh_source(self, source_id: str) -> dict[str, Any]:
        source = next((item for item in self.sources() if item.get("source_id") == source_id), None)
        if source is None:
            return {"status": "not_configured", "ingested": 0, "limitations": ["Source is not registered."]}
        if not source.get("enabled"):
            return {"status": "not_attempted", "ingested": 0, "limitations": ["Source is disabled."]}
        if source.get("kind") == "import":
            return {
                "status": "not_attempted",
                "ingested": 0,
                "limitations": ["Operator imports do not have a fetchable feed URL."],
            }
        if not source.get("url"):
            return {
                "status": "not_configured",
                "ingested": 0,
                "limitations": ["No public feed URL is configured for this source."],
            }
        fetch = self.fetcher.fetch(str(source["url"]))
        if fetch.get("status") != "ok":
            return {
                "status": "error",
                "ingested": 0,
                "limitations": [str(item) for item in (fetch.get("errors") or fetch.get("limitations") or [])][:5],
            }
        try:
            payload = json.loads(str(fetch.get("body_text") or fetch.get("body_preview") or ""))
        except (TypeError, ValueError) as exc:
            return {"status": "error", "ingested": 0, "limitations": [f"Feed was not valid JSON: {type(exc).__name__}"]}
        items = payload.get("indicators") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            return {"status": "error", "ingested": 0, "limitations": ["Feed must be a JSON array or an object with an 'indicators' array."]}
        result = self.ingest(items, source_id=source_id)
        result["source_url"] = fetch.get("final_url")
        result["limitations"] = list(result.get("limitations") or []) + list(fetch.get("limitations") or [])
        return result

    def ingest(self, items: Iterable[Any], *, source_id: str = "operator_import") -> dict[str, Any]:
        if source_id not in {str(item.get("source_id")) for item in self.sources()}:
            return {
                "status": "not_configured",
                "ingested": 0,
                "limitations": ["Indicators were not ingested because the source is not registered."],
            }
        repo = getattr(self.repos, "threat_indicators", None)
        if repo is None:
            return {"status": "not_configured", "ingested": 0, "limitations": ["Indicator repository is unavailable."]}

        stored = 0
        skipped = 0
        limitations: list[str] = []
        for raw in items or []:
            if not isinstance(raw, dict):
                skipped += 1
                continue
            kind = str(raw.get("kind") or "generic").strip().lower()
            if kind not in INDICATOR_KINDS:
                skipped += 1
                continue
            value = normalise_indicator_value(kind, raw.get("value"))
            if not value:
                skipped += 1
                continue
            status = str(raw.get("status") or "unverified")
            if status not in EVIDENCE_STATUSES:
                status = "unverified"
            try:
                ttl_days = min(365, max(1, int(raw.get("ttl_days") or DEFAULT_TTL_DAYS)))
            except (TypeError, ValueError):
                ttl_days = DEFAULT_TTL_DAYS
            expires_at = datetime.now(timezone.utc) + timedelta(days=ttl_days)
            dedupe_key = f"{source_id}:{kind}:{value}"
            repo.upsert(
                dedupe_key,
                {
                    "dedupe_key": dedupe_key,
                    "kind": kind,
                    "value": str(raw.get("value"))[:512],
                    "normalized_value": value,
                    "source_id": source_id,
                    "source_url": str(raw.get("source_url") or "")[:2048] or None,
                    "reference_url": str(raw.get("reference_url") or "")[:2048] or None,
                    "status": status,
                    "severity": round(clamp(raw.get("severity", 0.5)), 3),
                    "confidence": round(clamp(raw.get("confidence", 0.5)), 3),
                    "independently_verified": bool(raw.get("independently_verified")),
                    "description": str(raw.get("description") or "")[:1000],
                    "expires_at": expires_at,
                    "first_seen_at": str(raw.get("observed_at") or iso()),
                    "last_seen_at": iso(),
                },
            )
            stored += 1
        if skipped:
            limitations.append(f"{skipped} indicator record(s) were skipped because they were malformed.")
        return {
            "status": "ok" if stored else "not_attempted",
            "ingested": stored,
            "skipped": skipped,
            "limitations": limitations or ["No indicator records were supplied."],
        }

    @staticmethod
    def _candidate_values(values: Iterable[str]) -> list[str]:
        """Produce normalised forms for mixed caller-provided identifiers."""
        candidates = dedupe(value for value in values if str(value or "").strip())
        result: list[str] = list(candidates)
        for value in candidates:
            text = str(value).strip()
            if "@" in text:
                result.append(normalise_indicator_value("email", text))
            elif "://" in text:
                result.append(normalise_indicator_value("url", text))
                host = (urlsplit(text).hostname or "").strip()
                if host:
                    result.append(normalise_indicator_value("domain", host))
            elif "." in text and " " not in text:
                result.append(normalise_indicator_value("domain", text))
            else:
                result.append(normalise_indicator_value("generic", text))
        return dedupe(item for item in result if item)

    def match(
        self,
        values: Iterable[str],
        *,
        kinds: Iterable[str] | None = None,
        analysis_type: str = "offer",
    ) -> dict[str, Any]:
        candidates = self._candidate_values(values)
        if not candidates:
            return {
                "status": "not_attempted",
                "matches": [],
                "values_checked": [],
                "sources_attempted": [],
                "sources_succeeded": [],
                "limitations": ["No entity value was available for a threat-indicator lookup."],
                "indicators": [],
            }

        configured = [item for item in self.sources() if item.get("status") == "configured"]
        repo = getattr(self.repos, "threat_indicators", None)
        if repo is None:
            return {
                "status": "not_configured",
                "matches": [],
                "values_checked": candidates[:50],
                "sources_attempted": [],
                "sources_succeeded": [],
                "limitations": ["Threat-indicator repository is unavailable."],
                "indicators": [
                    make_indicator(
                        name="threat_intelligence_unavailable",
                        status="technical_limitation",
                        severity=0.0,
                        description="The local threat-indicator store could not be queried.",
                        source="threat indicator store",
                        confidence=0.8,
                    )
                ],
            }

        raw_matches = repo.active_matches(candidates, kinds)
        matches: dict[str, dict[str, Any]] = {}
        for row in raw_matches:
            key = str(row.get("normalized_value") or "")
            existing = matches.get(key)
            if existing is None or float(row.get("severity") or 0) > float(existing.get("severity") or 0):
                matches[key] = row

        indicators: list[dict[str, Any]] = []
        for row in matches.values():
            indicators.append(
                make_indicator(
                    name="threat_indicator_match",
                    status=str(row.get("status") or "unverified"),
                    severity=float(row.get("severity") or 0.5),
                    description=(
                        f"Threat source '{row.get('source_id')}' records this {row.get('kind')} as an indicator: "
                        f"{str(row.get('description') or 'no description supplied')}. "
                        "A store match is not proof of fraud."
                    ),
                    source=str(row.get("source_id") or "threat indicator store"),
                    reference_url=row.get("reference_url"),
                    confidence=float(row.get("confidence") or 0.5),
                    independently_verified=bool(row.get("independently_verified")),
                    expires_at=iso(row["expires_at"]) if hasattr(row.get("expires_at"), "astimezone") else row.get("expires_at"),
                )
            )

        limitations = [
            "Threat-indicator matches are decision-support signals, not proof of wrongdoing.",
            "Absence of a threat-indicator match does not establish legitimacy.",
        ]
        if not configured:
            limitations.append("No external threat feed is configured; only the local indicator store was queried.")
        status = "ok" if matches else ("not_configured" if not configured else "no_match")
        return {
            "status": status,
            "matches": list(matches.values()),
            "values_checked": candidates[:50],
            "sources_attempted": ["local_threat_indicator_store"],
            "sources_succeeded": ["local_threat_indicator_store"] if repo is not None else [],
            "limitations": limitations,
            "indicators": indicators,
        }


__all__ = [
    "BUILTIN_SOURCES",
    "DEFAULT_TTL_DAYS",
    "INDICATOR_KINDS",
    "ThreatIndicatorStore",
    "normalise_indicator_value",
]
