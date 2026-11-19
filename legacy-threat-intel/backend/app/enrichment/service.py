"""Indicator validation, local cache, external enrichment and evidence recording."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from app.enrichment.providers import AbuseIpdbProvider, EnrichmentProviderError, UrlhausProvider
from app.utils import make_id, parse_ts, retry_with_backoff, utcnow, validate_indicator

if TYPE_CHECKING:
    from app.config import Settings
    from app.db.repositories import Repositories

logger = logging.getLogger(__name__)


class EnrichmentService:
    def __init__(self, settings: "Settings", repos: "Repositories"):
        self.settings = settings
        self.repos = repos
        self.providers = {
            "ipv4": AbuseIpdbProvider(settings),
            "ipv6": AbuseIpdbProvider(settings),
            "domain": UrlhausProvider(settings),
            "url": UrlhausProvider(settings),
        }

    def enrich(self, indicator_type: str, value: str, *, force: bool = False) -> dict[str, Any]:
        validation = validate_indicator(indicator_type, value)
        if not validation["valid"]:
            return {"valid": False, "reason": validation["reason"], "value": value}
        kind = validation["type"]
        normalized = validation["normalized_value"]
        existing = self.repos.indicators.get(kind, normalized)
        ttl = timedelta(hours=max(1, self.settings.ti_cache_ttl_hours))
        if existing and not force:
            last_seen = parse_ts(existing.get("last_seen", utcnow()))
            if utcnow() - last_seen < ttl:
                return {"valid": True, "cached": True, "indicator": existing}

        source_entry: dict[str, Any] | None = None
        if validation["routable"] and self.settings.ti_enabled:
            provider = self.providers.get(kind)
            if provider and provider.available():
                try:
                    result = retry_with_backoff(
                        lambda: provider.lookup(normalized),
                        attempts=2,
                        base_delay=1.0,
                        exceptions=(EnrichmentProviderError,),
                    )
                    source_entry = {
                        "name": provider.name,
                        "reliability": provider.reliability,
                        "confidence": result["confidence"],
                        "reputation": result["reputation"],
                        "retrieved_at": utcnow(),
                        "tags": result.get("tags", []),
                        "detail": result.get("source_detail", {}),
                    }
                except Exception as exc:  # noqa: BLE001
                    logger.warning("enrichment failed type=%s value=%s error=%s", kind, normalized, exc)
            else:
                logger.debug("no configured provider for %s", kind)
        else:
            logger.debug("skipping external enrichment for non-routable indicator type=%s", kind)

        indicator = {
            "indicator_id": make_id("ind", kind, normalized),
            "type": kind,
            "value": validation["value"],
            "normalized_value": normalized,
            "is_malicious": bool((source_entry or {}).get("confidence", 0) >= self.settings.rule_malicious_confidence),
            "confidence": float((source_entry or {}).get("confidence") or 0),
            "reputation": (source_entry or {}).get("reputation") or "unverified",
            "reliability": float((source_entry or {}).get("reliability") or 0),
            "sources": [source_entry] if source_entry else [],
            "tags": list((source_entry or {}).get("tags", [])) or ["local_observation"],
            "first_seen": (existing or {}).get("first_seen", utcnow()),
            "last_seen": utcnow(),
            "routable": validation["routable"],
        }
        stored = self.repos.indicators.upsert(indicator)
        return {
            "valid": True,
            "cached": False,
            "external_lookup": bool(source_entry),
            "indicator": stored,
            "note": "Private/internal indicators are cached locally and never sent to external services."
            if not validation["routable"]
            else None,
        }

    def process_pending(self, limit: int = 100) -> dict[str, Any]:
        events = self.repos.events.find({"needs_enrichment": True}, sort_field="timestamp", limit=limit)
        processed = 0
        enriched = 0
        for event in events:
            for indicator in event.get("indicators") or []:
                if not isinstance(indicator, dict) or not indicator.get("value"):
                    continue
                result = self.enrich(str(indicator.get("type") or "ip"), str(indicator["value"]))
                if result.get("valid") and result.get("external_lookup"):
                    enriched += 1
            self.repos.events.update_many(
                {"event_id": event["event_id"]}, {"$set": {"needs_enrichment": False, "enriched_at": utcnow()}}
            )
            processed += 1
        return {"events_processed": processed, "external_enrichments": enriched}
