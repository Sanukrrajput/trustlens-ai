"""Reusable MongoDB connection, schema bootstrap, health and change-stream service."""

from __future__ import annotations

import logging
import threading
import time
from datetime import timezone
from typing import TYPE_CHECKING, Any, Callable, TypeVar

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import AutoReconnect, NetworkTimeout, OperationFailure, PyMongoError, ServerSelectionTimeoutError

from app.utils import utcnow

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger(__name__)
T = TypeVar("T")
RETRYABLE = (AutoReconnect, NetworkTimeout, ServerSelectionTimeoutError)

COLLECTIONS = (
    "security_events",
    "threat_indicators",
    "threat_detections",
    "incidents",
    "monitored_assets",
    "intelligence_sources",
    "collection_jobs",
    "model_registry",
    "notifications",
    "audit_logs",
    "system_health",
    "analyst_feedback",
    "platform_settings",
    "response_actions",
)

INDEXES: dict[str, list[tuple[list[tuple[str, int]], dict[str, Any]]]] = {
    "security_events": [
        ([(("dedupe_key"), ASCENDING)], {"unique": True, "name": "ux_event_dedupe"}),
        ([(("timestamp"), DESCENDING)], {"name": "ix_event_timestamp"}),
        ([(("ingested_at"), DESCENDING)], {"name": "ix_event_ingested"}),
        ([(("source_ip"), ASCENDING), (("timestamp"), DESCENDING)], {"name": "ix_event_source_ip_time"}),
        ([(("actor_user"), ASCENDING), (("timestamp"), DESCENDING)], {"name": "ix_event_user_time"}),
        ([(("event_type"), ASCENDING), (("timestamp"), DESCENDING)], {"name": "ix_event_type_time"}),
        ([(("asset_id"), ASCENDING), (("timestamp"), DESCENDING)], {"name": "ix_event_asset_time"}),
        ([(("expires_at"), ASCENDING)], {"name": "ttl_event", "expireAfterSeconds": 0}),
    ],
    "threat_indicators": [
        ([(("type"), ASCENDING), (("normalized_value"), ASCENDING)], {"unique": True, "name": "ux_indicator"}),
        ([(("is_malicious"), ASCENDING), (("confidence"), DESCENDING)], {"name": "ix_indicator_malicious"}),
        ([(("last_seen"), DESCENDING)], {"name": "ix_indicator_last_seen"}),
    ],
    "threat_detections": [
        ([(("detection_key"), ASCENDING)], {"unique": True, "name": "ux_detection_key"}),
        ([(("created_at"), DESCENDING)], {"name": "ix_detection_created"}),
        ([(("severity"), ASCENDING), (("risk_score"), DESCENDING)], {"name": "ix_detection_severity"}),
        ([(("type"), ASCENDING)], {"name": "ix_detection_type"}),
        ([(("expires_at"), ASCENDING)], {"name": "ttl_detection", "expireAfterSeconds": 0}),
    ],
    "incidents": [
        ([(("fingerprint"), ASCENDING)], {"name": "ix_incident_fingerprint"}),
        ([(("status"), ASCENDING), (("last_seen"), DESCENDING)], {"name": "ix_incident_status_time"}),
        ([(("severity"), ASCENDING)], {"name": "ix_incident_severity"}),
        ([(("expires_at"), ASCENDING)], {"name": "ttl_incident", "expireAfterSeconds": 0}),
    ],
    "monitored_assets": [
        ([(("asset_id"), ASCENDING)], {"unique": True, "name": "ux_asset_id"}),
        ([(("ip_addresses"), ASCENDING)], {"name": "ix_asset_ips"}),
    ],
    "intelligence_sources": [
        ([(("name"), ASCENDING)], {"unique": True, "name": "ux_source_name"}),
    ],
    "collection_jobs": [
        ([(("job_id"), ASCENDING)], {"unique": True, "name": "ux_job_id"}),
        ([(("started_at"), DESCENDING)], {"name": "ix_job_started"}),
        ([(("expires_at"), ASCENDING)], {"name": "ttl_job", "expireAfterSeconds": 0}),
    ],
    "model_registry": [
        ([(("name"), ASCENDING), (("version"), DESCENDING)], {"unique": True, "name": "ux_model_version"}),
        ([(("is_active"), ASCENDING)], {"name": "ix_model_active"}),
    ],
    "notifications": [
        ([(("dedupe_key"), ASCENDING)], {"unique": True, "name": "ux_notification_dedupe", "sparse": True}),
        ([(("created_at"), DESCENDING)], {"name": "ix_notification_created"}),
        ([(("status"), ASCENDING)], {"name": "ix_notification_status"}),
        ([(("expires_at"), ASCENDING)], {"name": "ttl_notification", "expireAfterSeconds": 0}),
    ],
    "audit_logs": [
        ([(("timestamp"), DESCENDING)], {"name": "ix_audit_time"}),
        ([(("actor"), ASCENDING)], {"name": "ix_audit_actor"}),
        ([(("expires_at"), ASCENDING)], {"name": "ttl_audit", "expireAfterSeconds": 0}),
    ],
    "system_health": [
        ([(("recorded_at"), DESCENDING)], {"name": "ix_health_time"}),
        ([(("expires_at"), ASCENDING)], {"name": "ttl_health", "expireAfterSeconds": 0}),
    ],
    "analyst_feedback": [
        ([(("detection_id"), ASCENDING)], {"name": "ix_feedback_detection"}),
        ([(("timestamp"), DESCENDING)], {"name": "ix_feedback_time"}),
    ],
    "platform_settings": [
        ([(("key"), ASCENDING)], {"unique": True, "name": "ux_setting_key"}),
    ],
    "response_actions": [
        ([(("action_id"), ASCENDING)], {"unique": True, "name": "ux_action_id"}),
        ([(("status"), ASCENDING)], {"name": "ix_action_status"}),
    ],
}

VALIDATORS: dict[str, dict[str, Any]] = {
    "security_events": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["event_id", "dedupe_key", "timestamp", "source_type", "event_type"],
            "properties": {
                "event_id": {"bsonType": "string"},
                "dedupe_key": {"bsonType": "string"},
                "timestamp": {"bsonType": "date"},
                "source_type": {"bsonType": "string"},
                "event_type": {"bsonType": "string"},
            },
        }
    },
    "incidents": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["incident_id", "title", "severity", "risk_score", "first_seen"],
            "properties": {
                "incident_id": {"bsonType": "string"},
                "title": {"bsonType": "string"},
                "severity": {"enum": ["informational", "low", "medium", "high", "critical"]},
                "risk_score": {"bsonType": ["int", "double"]},
                "first_seen": {"bsonType": "date"},
            },
        }
    },
}


class MongoDBService:
    """Owns client lifecycle, schema bootstrap, retries and change-stream support."""

    def __init__(self, settings: "Settings", client: Any | None = None):
        self.settings = settings
        self.client = client
        self.db: Any = None

    def connect(self) -> Any:
        if self.client is None:
            self.client = MongoClient(
                self.settings.mongodb_uri,
                maxPoolSize=50,
                minPoolSize=1,
                retryWrites=True,
                tz_aware=True,
                tzinfo=timezone.utc,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
            )
        self.db = self.client[self.settings.mongodb_db]
        self.ping()
        logger.info("MongoDB connected db=%s", self.settings.mongodb_db)
        return self.db

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
            self.db = None

    def collection(self, name: str) -> Any:
        if self.db is None:
            raise RuntimeError("MongoDBService.connect() must be called first")
        return self.db[name]

    def ping(self) -> float:
        start = time.perf_counter()
        self.execute(lambda: self.client.admin.command("ping"))
        return round((time.perf_counter() - start) * 1000, 2)

    def health(self) -> dict[str, Any]:
        try:
            latency = self.ping()
            server_info = self.execute(lambda: self.client.server_info())
            return {
                "status": "healthy",
                "latency_ms": latency,
                "server_version": server_info.get("version", "unknown"),
                "database": self.settings.mongodb_db,
                "checked_at": utcnow(),
            }
        except PyMongoError as exc:
            logger.error("MongoDB health check failed error=%s", exc)
            return {
                "status": "unhealthy",
                "error": str(exc),
                "database": self.settings.mongodb_db,
                "checked_at": utcnow(),
            }

    def setup(self) -> None:
        """Create collections, indexes and light validation. Safe to call repeatedly."""
        existing = set(self.execute(lambda: self.db.list_collection_names()))
        for name in COLLECTIONS:
            if name not in existing:
                try:
                    self.execute(lambda n=name: self.db.create_collection(n))
                    logger.info("Created collection %s", name)
                except OperationFailure as exc:
                    if "already exists" not in str(exc):
                        raise
        for name, indexes in INDEXES.items():
            try:
                self.execute(lambda n=name: self.db[n].create_indexes([_index(keys, opts) for keys, opts in indexes]))
            except (OperationFailure, NotImplementedError) as exc:
                logger.warning("Index creation skipped for %s: %s", name, exc)
        for name, validator in VALIDATORS.items():
            try:
                self.execute(
                    lambda n=name, v=validator: self.db.command(
                        {"collMod": n, "validator": v, "validationLevel": "moderate", "validationAction": "warn"}
                    )
                )
            except (OperationFailure, NotImplementedError, TypeError) as exc:
                logger.warning("Validator skipped for %s: %s", name, exc)

    def execute(self, fn: Callable[[], T], *, attempts: int = 3) -> T:
        """Run a MongoDB operation with bounded reconnection retries."""
        last_error: BaseException | None = None
        for attempt in range(1, attempts + 1):
            try:
                return fn()
            except RETRYABLE as exc:
                last_error = exc
                if attempt == attempts:
                    break
                delay = min(4.0, 0.25 * 2 ** (attempt - 1))
                logger.warning("Mongo retry %s/%s in %.2fs: %s", attempt, attempts, delay, exc)
                time.sleep(delay)
                try:
                    self.client.close()
                except Exception:  # noqa: BLE001
                    pass
                if self.db is not None:
                    self.db = self.client[self.settings.mongodb_db]
        assert last_error is not None
        raise last_error

    def watch_inserts(self, collection_name: str, on_insert: Callable[[dict[str, Any]], None], stop_event: threading.Event) -> None:
        """Thread target: change-stream listener with graceful fallback when unsupported."""
        if not self.settings.change_stream_enabled:
            return
        try:
            with self.collection(collection_name).watch(
                [{"$match": {"operationType": "insert"}}], max_await_time_ms=1000
            ) as stream:
                logger.info("Change stream listening on %s", collection_name)
                while not stop_event.is_set():
                    try:
                        change = stream.try_next()
                    except PyMongoError as exc:
                        logger.warning("Change stream error: %s", exc)
                        return
                    if change:
                        try:
                            on_insert(change.get("fullDocument") or {})
                        except Exception:  # noqa: BLE001 - never kill the listener
                            logger.exception("Change stream handler failed")
        except (OperationFailure, PyMongoError, NotImplementedError, AttributeError) as exc:
            logger.warning("Change streams unavailable, falling back to polling: %s", exc)


def _index(keys: list[tuple[str, int]], options: dict[str, Any]):
    from pymongo import IndexModel

    return IndexModel(keys, **options)
