"""External intelligence providers. Only public indicators are ever submitted."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import requests

from app.utils import RateLimiter, retry_with_backoff

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger(__name__)


class EnrichmentProviderError(RuntimeError):
    pass


class AbuseIpdbProvider:
    name = "abuseipdb"
    reliability = 0.8

    def __init__(self, settings: "Settings"):
        self.settings = settings
        self.limiter = RateLimiter(settings.ti_rate_limit_per_minute)

    def available(self) -> bool:
        return bool(self.settings.ti_enabled and self.settings.abuseipdb_api_key)

    def lookup(self, ip: str) -> dict[str, Any]:
        if not self.available():
            raise EnrichmentProviderError("ABUSEIPDB_API_KEY is not configured")
        if not self.limiter.wait(timeout=20):
            raise EnrichmentProviderError("AbuseIPDB rate limit exceeded")
        response = retry_with_backoff(
            lambda: requests.get(
                "https://api.abuseipdb.com/api/v2/check",
                headers={"Key": self.settings.abuseipdb_api_key, "Accept": "application/json"},
                params={"ipAddress": ip, "maxAgeInDays": 90, "verbose": ""},
                timeout=15,
            ),
            attempts=3,
            base_delay=1.0,
            exceptions=(requests.RequestException,),
        )
        if response.status_code == 429:
            raise EnrichmentProviderError("AbuseIPDB rate limit (HTTP 429)")
        response.raise_for_status()
        data = (response.json() or {}).get("data") or {}
        confidence = float(data.get("abuseConfidencePercentage") or 0) / 100.0
        return {
            "reputation": "malicious" if confidence >= 0.5 else "unknown",
            "confidence": round(min(1.0, confidence), 4),
            "is_malicious": confidence >= 0.5,
            "tags": ["abuseipdb", f"reports:{data.get('totalReports', 0)}"],
            "source_detail": {
                "usage_type": data.get("usageType"),
                "isp": data.get("isp"),
                "country_code": data.get("countryCode"),
                "last_reported_at": data.get("lastReportedAt"),
            },
        }


class UrlhausProvider:
    name = "urlhaus"
    reliability = 0.9

    def __init__(self, settings: "Settings"):
        self.settings = settings
        self.limiter = RateLimiter(settings.ti_rate_limit_per_minute)

    def available(self) -> bool:
        return bool(self.settings.ti_enabled)

    def lookup(self, indicator_type: str, value: str) -> dict[str, Any]:
        if not self.available():
            raise EnrichmentProviderError("TI_ENABLED=false")
        if not self.limiter.wait(timeout=20):
            raise EnrichmentProviderError("URLhaus rate limit exceeded")
        endpoint = "https://urlhaus-api.abuse.ch/v1/url/"
        payload = {"url": value}
        if indicator_type == "domain":
            endpoint = "https://urlhaus-api.abuse.ch/v1/host/"
            payload = {"host": value}
        headers = {"User-Agent": "authorized-threat-intel-platform/1.0"}
        if self.settings.urlhaus_api_key:
            headers["Auth-Key"] = self.settings.urlhaus_api_key
        response = retry_with_backoff(
            lambda: requests.post(endpoint, data=payload, headers=headers, timeout=15),
            attempts=3,
            base_delay=1.0,
            exceptions=(requests.RequestException,),
        )
        response.raise_for_status()
        data = response.json() or {}
        malicious = str(data.get("query_status")) == "ok"
        return {
            "reputation": "malicious" if malicious else "unknown",
            "confidence": 0.95 if malicious else 0.0,
            "is_malicious": malicious,
            "tags": ["urlhaus"] + ([data["threat"]] if data.get("threat") else []),
            "source_detail": {"threat": data.get("threat"), "urlhaus_reference": data.get("urlhaus_reference")},
        }
