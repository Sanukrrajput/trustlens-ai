"""APScheduler-based restart-safe automation with idempotent job execution."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.ingestion.manager import redact_error
from app.utils import make_id, utcnow

if TYPE_CHECKING:
    from app.config import Settings
    from app.db.repositories import Repositories

logger = logging.getLogger(__name__)


class JobScheduler:
    JOB_INTERVALS = {
        "collect": "collection_interval_minutes",
        "detect": "detection_interval_minutes",
        "enrich": "enrichment_interval_minutes",
        "correlate": "correlation_interval_minutes",
        "alert": "correlation_interval_minutes",
        "health": "health_interval_minutes",
    }

    def __init__(self, settings: "Settings", repos: "Repositories", services: dict[str, Any]):
        self.settings = settings
        self.repos = repos
        self.services = services
        self.scheduler = BackgroundScheduler(timezone="UTC", daemon=True)
        self._running: set[str] = set()

    def start(self) -> None:
        if not self.settings.scheduler_enabled:
            logger.info("Scheduler disabled by configuration")
            return
        for name, interval_field in self.JOB_INTERVALS.items():
            minutes = max(1, int(getattr(self.settings, interval_field)))
            self.scheduler.add_job(
                lambda job_name=name: self.run_job(job_name),
                trigger=IntervalTrigger(minutes=minutes),
                id=name,
                name=name,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=300,
                replace_existing=True,
            )
        self.scheduler.start()
        logger.info("Scheduler started jobs=%s", list(self.JOB_INTERVALS))

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.settings.scheduler_enabled,
            "running": self.scheduler.running,
            "jobs": [
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run": str(job.next_run_time) if job.next_run_time else None,
                }
                for job in self.scheduler.get_jobs()
            ],
        }

    def run_job(self, name: str) -> dict[str, Any]:
        if name in self._running:
            return {"job": name, "status": "skipped", "reason": "already running"}
        started = utcnow()
        self._running.add(name)
        status = "success"
        error = None
        result: dict[str, Any] = {}
        try:
            result = self._dispatch(name)
            if isinstance(result, dict) and result.get("error"):
                status = "failed"
                error = str(result["error"])
        except Exception as exc:  # noqa: BLE001 - scheduler must survive job faults
            status = "failed"
            error = redact_error(exc)
            logger.exception("scheduled job failed job=%s", name)
        finally:
            self._running.discard(name)
            finished = utcnow()
            self.repos.jobs.save(
                {
                    "job_id": make_id("job", name, started.isoformat()),
                    "name": name,
                    "trigger": "scheduled",
                    "started_at": started,
                    "finished_at": finished,
                    "duration_ms": round((finished - started).total_seconds() * 1000, 2),
                    "status": status,
                    "error": error,
                    "result": result if isinstance(result, dict) else {"value": str(result)},
                    "created_at": utcnow(),
                    "expires_at": utcnow() + timedelta(days=self.settings.job_retention_days),
                }
            )
        return {"job": name, "status": status, "error": error, "result": result}

    def _dispatch(self, name: str) -> dict[str, Any]:
        services = self.services
        if name == "collect":
            results = services["ingestion"].run_all()
            return {
                "sources": len(results),
                "records_inserted": sum(r.records_inserted for r in results),
                "errors": [error for r in results for error in r.errors],
            }
        if name == "detect":
            return services["detection"].process()
        if name == "enrich":
            return services["enrichment"].process_pending()
        if name == "correlate":
            return services["correlator"].correlate()
        if name == "alert":
            return services["alerts"].process()
        if name == "health":
            return services["health"].snapshot(self.status())
        raise ValueError(f"unknown job: {name}")
