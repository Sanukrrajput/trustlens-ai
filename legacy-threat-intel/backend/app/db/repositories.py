"""Repository classes: all MongoDB queries live here, never in route handlers."""

from __future__ import annotations

import logging
from typing import Any, Iterable

from pymongo import ASCENDING, DESCENDING, UpdateOne
from pymongo.errors import BulkWriteError

from app.db.mongo import MongoDBService
from app.utils import json_safe, make_id, utcnow

logger = logging.getLogger(__name__)


class Repositories:
    """Single access point for all typed repositories."""

    def __init__(self, mongo: MongoDBService):
        self.events = EventRepository(mongo)
        self.indicators = IndicatorRepository(mongo)
        self.detections = DetectionRepository(mongo)
        self.incidents = IncidentRepository(mongo)
        self.sources = SourceRepository(mongo)
        self.jobs = JobRepository(mongo)
        self.health = HealthRepository(mongo)
        self.feedback = FeedbackRepository(mongo)
        self.assets = AssetRepository(mongo)
        self.models = ModelRepository(mongo)
        self.notifications = NotificationRepository(mongo)
        self.audit = AuditRepository(mongo)
        self.settings = SettingsRepository(mongo)
        self.actions = ResponseActionRepository(mongo)


class BaseRepository:
    collection_name = ""

    def __init__(self, mongo: MongoDBService):
        self.mongo = mongo

    @property
    def coll(self):
        return self.mongo.collection(self.collection_name)

    def find_one(self, query: dict | None = None, projection: dict | None = None) -> dict | None:
        return self.mongo.execute(lambda: self.coll.find_one(query or {}, projection))

    def find(
        self,
        query: dict | None = None,
        *,
        sort_field: str = "timestamp",
        order: int = DESCENDING,
        limit: int = 100,
        projection: dict | None = None,
    ) -> list[dict]:
        cursor = self.coll.find(query or {}, projection).sort(sort_field, order).limit(max(0, int(limit)))
        return list(self.mongo.execute(lambda: cursor))

    def count(self, query: dict | None = None) -> int:
        return int(self.mongo.execute(lambda: self.coll.count_documents(query or {})))

    def distinct(self, field: str, query: dict | None = None) -> list[Any]:
        return list(self.mongo.execute(lambda: self.coll.distinct(field, query or {})))

    def aggregate(self, pipeline: list[dict]) -> list[dict]:
        return list(self.mongo.execute(lambda: self.coll.aggregate(pipeline)))

    def insert_one(self, document: dict) -> Any:
        return self.mongo.execute(lambda: self.coll.insert_one(document)).inserted_id

    def update_one(self, query: dict, update: dict, *, upsert: bool = False) -> dict:
        result = self.mongo.execute(lambda: self.coll.update_one(query, update, upsert=upsert))
        return {"matched": result.matched_count, "modified": result.modified_count, "upserted": str(result.upserted_id or "")}

    def update_many(self, query: dict, update: dict) -> int:
        result = self.mongo.execute(lambda: self.coll.update_many(query, update))
        return int(result.modified_count)

    def delete_one(self, query: dict) -> int:
        return int(self.mongo.execute(lambda: self.coll.delete_one(query)).deleted_count)

    def paginate(
        self,
        query: dict | None = None,
        *,
        page: int = 1,
        page_size: int = 25,
        sort_field: str = "timestamp",
        order: int = DESCENDING,
        projection: dict | None = None,
    ) -> dict[str, Any]:
        page = max(1, int(page))
        page_size = min(200, max(1, int(page_size)))
        total = self.count(query)
        cursor = self.coll.find(query or {}, projection).sort(sort_field, order).skip((page - 1) * page_size).limit(page_size)
        items = list(self.mongo.execute(lambda: cursor))
        return {
            "items": [json_safe(item) for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
        }


class EventRepository(BaseRepository):
    collection_name = "security_events"

    def bulk_upsert(self, events: Iterable[dict]) -> dict[str, int]:
        docs = list(events)
        if not docs:
            return {"inserted": 0, "duplicates": 0, "failed": 0}
        operations = [
            UpdateOne({"dedupe_key": doc["dedupe_key"]}, {"$setOnInsert": doc}, upsert=True)
            for doc in docs
        ]
        try:
            result = self.mongo.execute(lambda: self.coll.bulk_write(operations, ordered=False))
            return {
                "inserted": int(result.upserted_count),
                "duplicates": int(result.matched_count),
                "failed": 0,
            }
        except TypeError:
            # mongomock's bulk_write is not compatible with recent PyMongo;
            # fall back to individual upserts so tests remain representative.
            inserted = duplicates = failed = 0
            for doc in docs:
                try:
                    outcome = self.mongo.execute(
                        lambda d=doc: self.coll.update_one(
                            {"dedupe_key": d["dedupe_key"]}, {"$setOnInsert": d}, upsert=True
                        )
                    )
                    if outcome.upserted_id is not None:
                        inserted += 1
                    else:
                        duplicates += 1
                except Exception:  # noqa: BLE001
                    failed += 1
            return {"inserted": inserted, "duplicates": duplicates, "failed": failed}
        except BulkWriteError as exc:
            details = exc.details or {}
            inserted = int(details.get("nUpserted", 0))
            return {
                "inserted": inserted,
                "duplicates": max(0, len(docs) - inserted),
                "failed": len(details.get("writeErrors", [])),
            }

    def find_unprocessed(self, limit: int = 500) -> list[dict]:
        return self.find({"processed_at": {"$exists": False}}, sort_field="timestamp", limit=limit)

    def mark_processed(self, event_ids: list[str]) -> int:
        if not event_ids:
            return 0
        return self.update_many({"event_id": {"$in": event_ids}}, {"$set": {"processed_at": utcnow()}})

    def find_by_ids(self, event_ids: list[str]) -> list[dict]:
        return self.find({"event_id": {"$in": event_ids}}, sort_field="timestamp", limit=len(event_ids) or 1)

    def labeled(self, limit: int = 20000) -> list[dict]:
        return self.find({"label": {"$in": ["malicious", "benign"]}}, sort_field="timestamp", limit=limit)


class IndicatorRepository(BaseRepository):
    collection_name = "threat_indicators"

    def get(self, indicator_type: str, normalized_value: str) -> dict | None:
        return self.find_one({"type": indicator_type, "normalized_value": normalized_value})

    def upsert(self, indicator: dict) -> dict:
        """Merge feed evidence into an existing indicator without losing history."""
        query = {"type": indicator["type"], "normalized_value": indicator["normalized_value"]}
        existing = self.find_one(query)
        now = utcnow()
        if not existing:
            doc = dict(indicator)
            doc.setdefault("indicator_id", make_id("ind", indicator["type"], indicator["normalized_value"]))
            doc.setdefault("first_seen", now)
            doc.setdefault("last_seen", now)
            doc.setdefault("sources", list(indicator.get("sources", [])))
            self.mongo.execute(lambda: self.coll.update_one(query, {"$setOnInsert": doc}, upsert=True))
            return self.find_one(query) or doc
        sources = list(existing.get("sources", []))
        for source in indicator.get("sources", []):
            if not any(s.get("name") == source.get("name") and s.get("retrieved_at") == source.get("retrieved_at") for s in sources):
                sources.append(source)
        confidence = max(float(existing.get("confidence") or 0), float(indicator.get("confidence") or 0))
        update = {
            "$set": {
                "sources": sources[-50:],
                "last_seen": now,
                "confidence": confidence,
                "is_malicious": bool(existing.get("is_malicious") or indicator.get("is_malicious")),
                "reputation": indicator.get("reputation") or existing.get("reputation"),
                "tags": list(dict.fromkeys(list(existing.get("tags", [])) + list(indicator.get("tags", [])))),
            },
            "$min": {"first_seen": indicator.get("first_seen", existing.get("first_seen", now))},
        }
        self.update_one(query, update)
        return self.find_one(query) or existing

    def malicious_map(self) -> dict[str, dict]:
        result = {}
        for doc in self.find({"is_malicious": True}, sort_field="confidence", limit=5000):
            result[f"{doc.get('type')}:{doc.get('normalized_value')}"] = doc
        return result

    def search(self, query_text: str = "", kind: str = "", limit: int = 100) -> list[dict]:
        query: dict[str, Any] = {}
        if kind:
            query["type"] = kind
        if query_text:
            query["normalized_value"] = {"$regex": query_text, "$options": "i"}
        return self.find(query, sort_field="last_seen", limit=limit)


class DetectionRepository(BaseRepository):
    collection_name = "threat_detections"

    def upsert(self, detection: dict) -> dict:
        key = detection["detection_key"]
        query = {"detection_key": key}
        existing = self.find_one(query)
        if not existing:
            doc = dict(detection)
            doc.setdefault("detection_id", make_id("det", key))
            self.mongo.execute(lambda: self.coll.update_one(query, {"$setOnInsert": doc}, upsert=True))
        else:
            self.update_one(
                query,
                {
                    "$set": {
                        "last_seen": utcnow(),
                        "risk_score": detection.get("risk_score", existing.get("risk_score", 0)),
                        "severity": detection.get("severity", existing.get("severity", "informational")),
                        "confidence": detection.get("confidence", existing.get("confidence")),
                    },
                    "$addToSet": {
                        "event_ids": {"$each": detection.get("event_ids", [])},
                        "indicator_ids": {"$each": detection.get("indicator_ids", [])},
                    },
                },
            )
        return self.find_one(query) or detection


class IncidentRepository(BaseRepository):
    collection_name = "incidents"

    def find_active_by_fingerprint(self, fingerprint: str) -> dict | None:
        matches = self.find(
            {"fingerprint": fingerprint, "status": {"$nin": ["closed", "resolved"]}},
            sort_field="last_seen",
            limit=1,
        )
        return matches[0] if matches else None

    def upsert(self, incident: dict) -> dict:
        existing = self.find_active_by_fingerprint(incident["fingerprint"])
        if not existing:
            doc = dict(incident)
            doc.setdefault("incident_id", make_id("inc", incident["fingerprint"], utcnow().isoformat()))
            self.insert_one(doc)
            return doc
        event_ids = list(dict.fromkeys(existing.get("event_ids", []) + incident.get("event_ids", [])))
        detection_ids = list(dict.fromkeys(existing.get("detection_ids", []) + incident.get("detection_ids", [])))
        timeline = list(existing.get("timeline", []))
        for entry in incident.get("timeline", []):
            if entry not in timeline:
                timeline.append(entry)
        self.update_one(
            {"_id": existing["_id"]},
            {
                "$set": {
                    "last_seen": incident.get("last_seen", utcnow()),
                    "risk_score": max(float(existing.get("risk_score", 0)), float(incident.get("risk_score", 0))),
                    "severity": incident.get("severity", existing.get("severity")),
                    "event_ids": event_ids,
                    "detection_ids": detection_ids,
                    "indicators": list(dict.fromkeys(existing.get("indicators", []) + incident.get("indicators", []))),
                    "affected_assets": list(dict.fromkeys(existing.get("affected_assets", []) + incident.get("affected_assets", []))),
                    "timeline": timeline[-200:],
                    "recommended_steps": incident.get("recommended_steps", existing.get("recommended_steps", [])),
                    "updated_at": utcnow(),
                }
            },
        )
        return self.find_one({"_id": existing["_id"]}) or existing

    def set_status(self, incident_id: str, status: str, note: str = "") -> dict:
        self.update_one(
            {"incident_id": incident_id},
            {
                "$set": {"status": status, "updated_at": utcnow()},
                "$push": {"timeline": {"at": utcnow(), "event": f"status_changed:{status}", "note": note}},
            },
        )
        return self.find_one({"incident_id": incident_id}) or {}


class SourceRepository(BaseRepository):
    collection_name = "intelligence_sources"

    def upsert_status(self, status: dict) -> None:
        self.update_one(
            {"name": status["name"]},
            {"$set": status, "$setOnInsert": {"created_at": utcnow()}},
            upsert=True,
        )


class JobRepository(BaseRepository):
    collection_name = "collection_jobs"

    def save(self, job: dict) -> None:
        self.update_one({"job_id": job["job_id"]}, {"$set": job}, upsert=True)


class HealthRepository(BaseRepository):
    collection_name = "system_health"

    def write(self, snapshot: dict) -> None:
        self.insert_one(snapshot)
        current = dict(snapshot)
        current["_id"] = "current"
        self.update_one({"_id": "current"}, {"$set": current}, upsert=True)

    def current(self) -> dict | None:
        return self.find_one({"_id": "current"})


class FeedbackRepository(BaseRepository):
    collection_name = "analyst_feedback"

    def add(self, feedback: dict) -> dict:
        doc = dict(feedback)
        doc.setdefault("feedback_id", make_id("fb", utcnow().isoformat()))
        doc.setdefault("timestamp", utcnow())
        self.insert_one(doc)
        return doc


class AssetRepository(BaseRepository):
    collection_name = "monitored_assets"

    def upsert(self, asset: dict) -> dict:
        query = {"asset_id": asset["asset_id"]}
        values = {key: value for key, value in asset.items() if key != "created_at"}
        self.update_one(
            query,
            {
                "$set": values,
                "$setOnInsert": {"created_at": asset.get("created_at") or utcnow()},
            },
            upsert=True,
        )
        return self.find_one(query) or asset

    def by_ip(self) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for doc in self.find({}, sort_field="criticality", limit=5000):
            for ip in doc.get("ip_addresses", []):
                result[str(ip)] = doc
        return result

    def by_id(self) -> dict[str, dict]:
        return {str(doc["asset_id"]): doc for doc in self.find({}, sort_field="criticality", limit=5000)}


class ModelRepository(BaseRepository):
    collection_name = "model_registry"

    def register(self, doc: dict) -> dict:
        query = {"name": doc["name"], "version": doc["version"]}
        self.update_one(query, {"$set": doc}, upsert=True)
        if doc.get("is_active"):
            self.update_many(
                {"name": doc["name"], "version": {"$ne": doc["version"]}},
                {"$set": {"is_active": False}},
            )
        return self.find_one(query) or doc

    def active(self, name: str) -> dict | None:
        return self.find_one({"name": name, "is_active": True})


class NotificationRepository(BaseRepository):
    collection_name = "notifications"

    def create(self, notification: dict) -> bool:
        doc = dict(notification)
        doc.setdefault("notification_id", make_id("ntf", doc.get("dedupe_key", utcnow().isoformat())))
        doc.setdefault("created_at", utcnow())
        doc.setdefault("status", "pending")
        try:
            self.mongo.execute(lambda: self.coll.update_one({"dedupe_key": doc["dedupe_key"]}, {"$setOnInsert": doc}, upsert=True))
            return True
        except BulkWriteError:
            return False

    def mark_read(self, notification_id: str) -> int:
        return self.update_many({"notification_id": notification_id}, {"$set": {"read": True, "read_at": utcnow()}})


class AuditRepository(BaseRepository):
    collection_name = "audit_logs"

    def write(self, action: str, actor: str, details: dict | None = None, **extra: Any) -> dict:
        doc = {
            "audit_id": make_id("aud", action, actor, utcnow().isoformat()),
            "action": action,
            "actor": actor,
            "details": json_safe(details or {}),
            "timestamp": utcnow(),
            "expires_at": None,
            **json_safe(extra),
        }
        self.insert_one(doc)
        return doc


class SettingsRepository(BaseRepository):
    collection_name = "platform_settings"

    def get(self, key: str, default: Any = None) -> Any:
        doc = self.find_one({"key": key})
        return doc.get("value", default) if doc else default

    def set(self, key: str, value: Any, actor: str = "system") -> dict:
        doc = {"key": key, "value": json_safe(value), "updated_at": utcnow(), "updated_by": actor}
        self.update_one({"key": key}, {"$set": doc}, upsert=True)
        return doc


class ResponseActionRepository(BaseRepository):
    collection_name = "response_actions"

    def create(self, action: dict) -> dict:
        self.update_one({"action_id": action["action_id"]}, {"$set": action}, upsert=True)
        return self.find_one({"action_id": action["action_id"]}) or action

    def approve(self, action_id: str, approver: str, note: str) -> dict:
        self.update_one(
            {"action_id": action_id},
            {
                "$set": {
                    "status": "approved",
                    "approved_by": approver,
                    "approval_note": note,
                    "approved_at": utcnow(),
                }
            },
        )
        return self.find_one({"action_id": action_id}) or {}
