"""Orchestrates authorized collectors with retries, deduplication and job records."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from app.ingestion.application_logs import ApplicationLogSource
from app.ingestion.base import CollectionResult, IngestionSource
from app.ingestion.threat_intel import UrlhausFeedSource
from app.ingestion.windows_eventlog import WindowsEventLogFileSource, WindowsEventLogSource
from app.utils import make_id, retry_with_backoff, utcnow

if TYPE_CHECKING:
    from app.config import Settings
    from app.db.mongo import MongoDBService
    from app.db.repositories import Repositories

logger = logging.getLogger(__name__)


class IngestionManager:
    def __init__(self, settings: "Settings", mongo: MongoDBService, repos: "Repositories"):
        self.settings = settings
        self.mongo = mongo
        self.repos = repos

    def sources(self) -> list[IngestionSource]:
        return [
            WindowsEventLogSource(self.settings),
            WindowsEventLogFileSource(self.settings),
            ApplicationLogSource(self.settings),
            UrlhausFeedSource(self.settings),
        ]

    def source_by_name(self, name: str) -> IngestionSource | None:
        return next((source for source in self.sources() if source.name == name), None)

    def list_sources(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for source in self.sources():
            status = source.status_document()
            stored = self.repos.sources.find_one({"name": source.name}) or {}
            stored.pop("_id", None)
            status.update({k: v for k, v in stored.items() if k not in {"name", "metadata"}})
            stored_meta = stored.get("metadata") or {}
            status["metadata"] = {**stored_meta, **(status.get("metadata") or {})}
            status["cursors"] = stored_meta.get("cursors", {})
            result.append(status)
        return result

    def _since_for(self, source: IngestionSource) -> Any:
        stored = self.repos.sources.find_one({"name": source.name}) or {}
        last = ((stored.get("metadata") or {}).get("cursors") or {}).get("last_event_at")
        from app.utils import parse_ts

        return parse_ts(last) if last else None

    def _add_asset_context(self, event: Any) -> None:
        """Attach asset identity/criticality from the authorized asset inventory."""
        ip_map = self.repos.assets.by_ip()
        id_map = self.repos.assets.by_id()
        candidate = None
        for value in (event.source_ip, event.destination_ip, event.host, event.asset_id):
            if not value:
                continue
            candidate = ip_map.get(str(value)) or id_map.get(str(value))
            if candidate:
                break
        if candidate:
            event.asset_id = str(candidate.get("asset_id"))
            event.asset_criticality = int(candidate.get("criticality") or 0)

    def _prepare(self, event: Any, source: IngestionSource) -> dict[str, Any]:
        self._add_asset_context(event)
        doc = event.model_dump(mode="json")
        doc.update(
            ingested_at=utcnow(),
            expires_at=utcnow() + timedelta(days=self.settings.event_retention_days),
            needs_enrichment=bool(event.indicators),
            source_metadata={"source_name": source.name, "source_type": source.source_type},
            schema_version="1.0",
        )
        return doc

    def run_source(self, name: str) -> CollectionResult:
        started = utcnow()
        source = self.source_by_name(name)
        if source is None:
            result = CollectionResult(name, False, started, utcnow(), errors=[f"unknown source: {name}"])
            self._save_job(result)
            return result

        result = CollectionResult(source.name, False, started, utcnow())
        if not source.is_authorized():
            error = "source is not in AUTHORIZED_SOURCES/ENABLED_SOURCES"
            result.errors.append(error)
            self.repos.sources.upsert_status(
                source.status_document(available=False, reason=error, error=error)
            )
            self._save_job(result)
            return result

        try:
            available, reason = source.check_available()
            if not available:
                result.errors.append(reason)
                self.repos.sources.upsert_status(source.status_document(available=False, reason=reason))
                self._save_job(result)
                return result

            events = retry_with_backoff(
                lambda: source.collect(self._since_for(source)),
                attempts=3,
                base_delay=0.5,
                exceptions=(Exception,),
            )
            result.records_read = len(events)
            prepared = [self._prepare(event, source) for event in events]
            stats = self.repos.events.bulk_upsert(prepared)
            result.records_inserted = stats["inserted"]
            result.duplicates = stats["duplicates"]
            if stats["failed"]:
                result.errors.append(f"{stats['failed']} bulk write errors")
            result.success = True
            latest = max((event.timestamp for event in events), default=None)
            self.repos.sources.upsert_status(
                source.status_document(
                    available=True,
                    reason=reason,
                    metadata={
                        "records_collected": len(events),
                        "cursors": {"last_event_at": latest.isoformat() if latest else None},
                    },
                )
            )
            result.metadata["latest_event_at"] = latest.isoformat() if latest else None
        except Exception as exc:  # noqa: BLE001 - collector faults must not kill scheduler
            result.errors.append(redact_error(exc))
            logger.exception("collection failed source=%s", source.name)
            self.repos.sources.upsert_status(
                source.status_document(available=False, reason="collection failed", error=redact_error(exc))
            )
        finally:
            result.finished_at = utcnow()
            self._save_job(result)
        return result

    def run_all(self) -> list[CollectionResult]:
        results = []
        for source in self.sources():
            if source.is_authorized():
                results.append(self.run_source(source.name))
            else:
                status = source.status_document(available=False, reason="disabled by configuration")
                self.repos.sources.upsert_status(status)
        return results

    def _save_job(self, result: CollectionResult) -> None:
        job = result.to_doc()
        job.update(
            job_id=make_id("job", result.source, result.started_at.isoformat()),
            created_at=utcnow(),
            expires_at=utcnow() + timedelta(days=self.settings.job_retention_days),
        )
        self.repos.jobs.save(job)


def redact_error(exc: BaseException) -> str:
    from app.utils import redact

    return redact(f"{type(exc).__name__}: {exc}", 1000)
