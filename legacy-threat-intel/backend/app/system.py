"""System health snapshot composed from real database and service state."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.utils import utcnow

if TYPE_CHECKING:
    from app.config import Settings
    from app.db.mongo import MongoDBService
    from app.db.repositories import Repositories

VERSION = "1.0.0"


class SystemHealthService:
    def __init__(self, settings: "Settings", mongo: MongoDBService, repos: "Repositories"):
        self.settings = settings
        self.mongo = mongo
        self.repos = repos
        self.started_at = utcnow()

    def snapshot(self, scheduler_status: dict[str, Any] | None = None) -> dict[str, Any]:
        db_health = self.mongo.health()
        source_health = self.repos.sources.find({}, sort_field="last_checked_at", limit=50)
        snapshot = {
            "recorded_at": utcnow(),
            "version": VERSION,
            "environment": self.settings.environment,
            "uptime_seconds": round((utcnow() - self.started_at).total_seconds(), 1),
            "database": db_health,
            "scheduler": scheduler_status or {"enabled": self.settings.scheduler_enabled},
            "sources": [
                {
                    "name": s.get("name"),
                    "status": s.get("status"),
                    "available": s.get("available"),
                    "reason": s.get("reason"),
                }
                for s in source_health
            ],
            "counts": {
                "events": self.repos.events.count(),
                "detections": self.repos.detections.count(),
                "open_incidents": self.repos.incidents.count({"status": {"$nin": ["closed", "resolved"]}}),
                "indicators": self.repos.indicators.count(),
                "notifications": self.repos.notifications.count(),
            },
        }
        snapshot["status"] = "healthy" if db_health.get("status") == "healthy" else "degraded"
        self.repos.health.write(snapshot)
        return snapshot
