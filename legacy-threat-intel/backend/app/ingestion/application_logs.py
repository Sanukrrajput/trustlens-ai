"""Authorized application/API log file collector (JSON Lines)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.ingestion.base import IngestionSource
from app.schemas import NormalizedEvent
from app.utils import redact

if TYPE_CHECKING:
    from app.config import Settings


def _first(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return None


class ApplicationLogSource(IngestionSource):
    name = "application_log"
    source_type = "application_log"

    def _path(self) -> Path | None:
        raw = (self.settings.application_log_path or "").strip()
        return Path(raw) if raw else None

    def check_available(self) -> tuple[bool, str]:
        path = self._path()
        if path is None:
            return False, "APPLICATION_LOG_PATH is not configured"
        if not path.is_file():
            return False, f"application log file not found: {path}"
        return True, "authorized application log file available"

    def collect(self, since: datetime | None = None) -> list[NormalizedEvent]:
        available, reason = self.check_available()
        if not available:
            raise RuntimeError(reason)
        assert self._path() is not None
        events: list[NormalizedEvent] = []
        with self._path().open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    self.logger.warning("invalid JSON line skipped line=%s", line_number)
                    continue
                if not isinstance(record, dict):
                    continue
                timestamp = _first(record, "timestamp", "time", "@timestamp", "event_time")
                if since and timestamp:
                    try:
                        from app.utils import parse_ts

                        if parse_ts(timestamp) < since:
                            continue
                    except ValueError:
                        pass
                outcome = str(_first(record, "outcome", "result", "status", "") or "").lower()
                event_type = str(
                    _first(record, "event_type", "type", "event", "action") or "application_event"
                ).lower()
                if event_type in {"login", "auth", "authentication"}:
                    event_type = "auth_success" if "success" in outcome or outcome == "200" else "auth_failure"
                elif event_type == "api_request" and outcome in {"429", "rate_limited"}:
                    event_type = "api_rate_limit"
                source_ip = _first(record, "source_ip", "src_ip", "ip", "client_ip")
                destination_ip = _first(record, "destination_ip", "dst_ip", "server_ip")
                domain = _first(record, "domain", "hostname", "host")
                url = _first(record, "url", "request_url", "uri")
                file_hash = _first(record, "file_hash", "sha256", "md5", "hash")
                user = _first(record, "actor_user", "user", "username", "user_id")
                raw_line = line
                line_hash = hashlib.sha256(raw_line.encode("utf-8", errors="replace")).hexdigest()
                indicators: list[dict[str, str]] = []
                if source_ip:
                    indicators.append({"type": "ip", "value": str(source_ip)})
                if destination_ip:
                    indicators.append({"type": "ip", "value": str(destination_ip)})
                if domain:
                    indicators.append({"type": "domain", "value": str(domain)})
                if url:
                    indicators.append({"type": "url", "value": str(url)})
                if file_hash:
                    indicators.append({"type": "hash", "value": str(file_hash)})

                events.append(
                    NormalizedEvent(
                        event_id=f"evt_app_{line_hash[:24]}",
                        source_type="application_log",
                        source_name=self.name,
                        source_id=f"{self._path().name}:{line_number}",
                        host=str(domain or _first(record, "host", "server", "") or "")[:256],
                        event_type=event_type,
                        event_action=str(_first(record, "action", "method", "") or event_type)[:64],
                        timestamp=timestamp or datetime.utcnow(),
                        actor_user=str(user)[:256] if user else None,
                        source_ip=str(source_ip)[:64] if source_ip else None,
                        destination_ip=str(destination_ip)[:64] if destination_ip else None,
                        destination_port=int(record["destination_port"]) if record.get("destination_port") else None,
                        protocol=str(_first(record, "protocol", "scheme", "") or None)[:32],
                        destination_host=str(domain)[:256] if domain else None,
                        url=str(url)[:2048] if url else None,
                        domain=str(domain)[:253] if domain else None,
                        file_hash=str(file_hash)[:128] if file_hash else None,
                        message=redact(str(_first(record, "message", "msg", "description", "") or ""), 1000),
                        raw=redact(raw_line, 4000),
                        tags=[f"source:{self.name}"],
                        indicators=indicators,
                        metadata={k: str(v)[:200] for k, v in list(record.items())[:30] if k not in {"message", "raw"}},
                        dedupe_key=f"evt_app_{line_hash}",
                        label=record.get("label") if record.get("label") in {"malicious", "benign"} else None,
                    )
                )
        self.logger.info("collected=%s from=%s", len(events), self._path())
        return events
