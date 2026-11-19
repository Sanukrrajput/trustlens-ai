"""Configurable public threat-intelligence feed ingestion (URLhaus).

Only public feed content is downloaded. Private logs, credentials and personal
data are never sent to external services.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import requests

from app.ingestion.base import IngestionSource
from app.schemas import NormalizedEvent
from app.utils import RateLimiter, make_id, parse_ts, redact, utcnow

if TYPE_CHECKING:
    from app.config import Settings

URLHAUS_RECENT_CSV = "https://urlhaus.abuse.ch/downloads/csv_recent/"


class UrlhausFeedSource(IngestionSource):
    name = "urlhaus_feed"
    source_type = "threat_intelligence"

    def __init__(self, settings: "Settings"):
        super().__init__(settings)
        self.limiter = RateLimiter(max(2, settings.ti_rate_limit_per_minute))

    def check_available(self) -> tuple[bool, str]:
        if not self.settings.ti_enabled:
            return False, "TI_ENABLED=false"
        if not self.settings.urlhaus_feed_enabled:
            return False, "URLHAUS_FEED_ENABLED=false"
        return True, "URLhaus public feed configured"

    def collect(self, since: datetime | None = None) -> list[NormalizedEvent]:
        available, reason = self.check_available()
        if not available:
            raise RuntimeError(reason)
        if not self.limiter.wait():
            raise RuntimeError("threat intelligence rate limit exceeded")
        response = requests.get(
            URLHAUS_RECENT_CSV,
            timeout=30,
            headers={"User-Agent": "authorized-threat-intel-platform/1.0"},
        )
        response.raise_for_status()
        events: list[NormalizedEvent] = []
        reader = csv.reader(io.StringIO(response.text))
        max_records = self.settings.ti_feed_max_records
        for row in reader:
            if len(events) >= max_records:
                break
            if not row or row[0].startswith("#"):
                continue
            if len(row) < 7:
                continue
            url = row[2].strip()
            if not url.startswith(("http://", "https://")):
                continue
            try:
                added = parse_ts(row[1])
            except ValueError:
                added = utcnow()
            if since and added < since:
                continue
            host = (urlparse(url).hostname or "")[:253]
            indicators = [{"type": "url", "value": url}]
            if host:
                indicators.append({"type": "domain", "value": host})
            events.append(
                NormalizedEvent(
                    event_id=make_id("evt", self.name, row[0]),
                    source_type="threat_intelligence",
                    source_name=self.name,
                    source_id=str(row[0]),
                    event_type="ti_feed",
                    event_action="malware_url_reported",
                    timestamp=added,
                    url=url[:2048],
                    domain=host or None,
                    message=redact(f"URLhaus reported {row[6] if len(row) > 6 else 'malicious'} URL", 500),
                    tags=["ti_feed", f"threat:{row[6] if len(row) > 6 else 'unknown'}"],
                    indicators=indicators,
                    dedupe_key=make_id("evt", self.name, row[0]),
                    metadata={"urlhaus_id": row[0], "threat": row[6] if len(row) > 6 else ""},
                    label="malicious",
                )
            )
        return events
