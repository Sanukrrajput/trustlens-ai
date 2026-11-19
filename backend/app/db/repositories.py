"""Repository layer: all database access is centralised here."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from bson import ObjectId
from pymongo import DESCENDING

from app.db.mongo import MongoDBService


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_id(value: str | ObjectId) -> ObjectId:
    return value if isinstance(value, ObjectId) else ObjectId(value)


def public(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if doc is None:
        return None
    copy = dict(doc)
    oid = copy.pop("_id", None)
    if oid is not None:
        copy["id"] = str(oid)
    return copy


class BaseRepository:
    collection_name = ""

    def __init__(self, mongo: MongoDBService) -> None:
        self.mongo = mongo

    @property
    def col(self):
        return self.mongo.collection(self.collection_name)

    def insert(self, document: dict[str, Any]) -> dict[str, Any]:
        doc = dict(document)
        doc.setdefault("created_at", utcnow())
        result = self.col.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc

    def get(self, id_value: str) -> dict[str, Any] | None:
        try:
            return self.col.find_one({"_id": as_id(id_value)})
        except Exception:
            return None

    def update(self, id_value: str, changes: dict[str, Any]) -> dict[str, Any] | None:
        changes = {key: value for key, value in changes.items() if key not in {"_id", "id"}}
        changes["updated_at"] = utcnow()
        self.col.update_one({"_id": as_id(id_value)}, {"$set": changes})
        return self.get(id_value)

    def delete(self, id_value: str) -> bool:
        return self.col.delete_one({"_id": as_id(id_value)}).deleted_count > 0

    def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        return self.col.find_one(query)

    def find(
        self,
        query: dict[str, Any] | None = None,
        *,
        sort: list[tuple[str, int]] | None = None,
        skip: int = 0,
        limit: int = 50,
        projection: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        cursor = self.col.find(query or {}, projection)
        if sort:
            cursor = cursor.sort(sort)
        return list(cursor.skip(skip).limit(limit))

    def count(self, query: dict[str, Any] | None = None) -> int:
        return self.col.count_documents(query or {})


class UserRepository(BaseRepository):
    collection_name = "users"

    def get_by_email(self, email: str) -> dict[str, Any] | None:
        return self.col.find_one({"email": email.lower().strip()})

    def create(self, document: dict[str, Any]) -> dict[str, Any]:
        document["email"] = document["email"].lower().strip()
        return self.insert(document)

    def set_verified(self, user_id: str) -> None:
        self.col.update_one({"_id": as_id(user_id)}, {"$set": {"email_verified": True, "updated_at": utcnow()}})

    def set_role(self, user_id: str, role: str) -> None:
        self.col.update_one({"_id": as_id(user_id)}, {"$set": {"role": role, "updated_at": utcnow()}})


class AnalysisRepository(BaseRepository):
    collection_name = "fraud_analyses"

    def create(self, document: dict[str, Any]) -> dict[str, Any]:
        return self.insert(document)

    def for_user(
        self,
        user_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        analysis_type: str | None = None,
        min_score: int | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        query: dict[str, Any] = {"user_id": user_id}
        if analysis_type:
            query["analysis_type"] = analysis_type
        if min_score is not None:
            query["risk.score"] = {"$gte": min_score}
        total = self.count(query)
        docs = self.find(
            query,
            sort=[("created_at", DESCENDING)],
            skip=(page - 1) * page_size,
            limit=page_size,
        )
        return docs, total

    def find_idempotent(self, user_id: str, client_request_id: str) -> dict[str, Any] | None:
        return self.col.find_one({"user_id": user_id, "client_request_id": client_request_id})

    def stats_for_user(self, user_id: str) -> dict[str, Any]:
        pipeline = [
            {"$match": {"user_id": user_id}},
            {
                "$group": {
                    "_id": None,
                    "total": {"$sum": 1},
                    "high_risk": {"$sum": {"$cond": [{"$gte": ["$risk.score", 60]}, 1, 0]}},
                    "average_score": {"$avg": "$risk.score"},
                }
            },
        ]
        result = list(self.col.aggregate(pipeline))
        if not result:
            return {"total": 0, "high_risk": 0, "average_score": 0}
        row = result[0]
        return {
            "total": row.get("total", 0),
            "high_risk": row.get("high_risk", 0),
            "average_score": round(row.get("average_score") or 0, 1),
        }

    def distribution_for_user(self, user_id: str) -> list[dict[str, Any]]:
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {"_id": "$risk.category", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        return [{"category": row.get("_id") or "unknown", "count": row["count"]} for row in self.col.aggregate(pipeline)]

    def global_stats(self) -> dict[str, Any]:
        pipeline = [
            {
                "$group": {
                    "_id": None,
                    "total": {"$sum": 1},
                    "high_risk": {"$sum": {"$cond": [{"$gte": ["$risk.score", 60]}, 1, 0]}},
                    "average_score": {"$avg": "$risk.score"},
                }
            }
        ]
        rows = list(self.col.aggregate(pipeline))
        row = rows[0] if rows else {}
        return {
            "total": row.get("total", 0),
            "high_risk": row.get("high_risk", 0),
            "average_score": round(row.get("average_score") or 0, 1),
        }

    def pattern_counts(self, limit: int = 10) -> list[dict[str, Any]]:
        pipeline = [
            {"$unwind": "$indicators"},
            {"$match": {"indicators.severity": {"$gte": 0.4}}},
            {"$group": {"_id": "$indicators.name", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": limit},
        ]
        return [{"name": row.get("_id"), "count": row["count"]} for row in self.col.aggregate(pipeline)]


class NotificationRepository(BaseRepository):
    collection_name = "notifications"

    def create_deduped(self, document: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        dedupe_key = document.get("dedupe_key")
        if dedupe_key and self.col.find_one({"dedupe_key": dedupe_key}):
            return document, False
        return self.insert(document), True

    def for_user(self, user_id: str, page: int = 1, page_size: int = 20, unread_only: bool = False):
        query: dict[str, Any] = {"user_id": user_id}
        if unread_only:
            query["read"] = False
        total = self.count(query)
        docs = self.find(query, sort=[("created_at", DESCENDING)], skip=(page - 1) * page_size, limit=page_size)
        return docs, total

    def mark_read(self, user_id: str, notification_id: str) -> dict[str, Any] | None:
        self.col.update_one(
            {"_id": as_id(notification_id), "user_id": user_id},
            {"$set": {"read": True, "read_at": utcnow()}},
        )
        return self.get(notification_id)


class MonitoringRepository(BaseRepository):
    collection_name = "monitoring_tasks"

    def for_user(self, user_id: str) -> list[dict[str, Any]]:
        return self.find({"user_id": user_id}, sort=[("created_at", DESCENDING)], limit=200)

    def all_enabled(self) -> list[dict[str, Any]]:
        return self.find({"enabled": True}, limit=1000)

    def for_user_id(self, user_id: str, task_id: str) -> dict[str, Any] | None:
        return self.col.find_one({"_id": as_id(task_id), "user_id": user_id})


class CompanyRepository(BaseRepository):
    collection_name = "companies"

    def by_fingerprint(self, fingerprint: str) -> dict[str, Any] | None:
        return self.col.find_one({"name_fingerprint": fingerprint})

    def upsert(self, fingerprint: str, document: dict[str, Any]) -> dict[str, Any]:
        document["name_fingerprint"] = fingerprint
        document["updated_at"] = utcnow()
        self.col.update_one({"name_fingerprint": fingerprint}, {"$set": document}, upsert=True)
        return self.col.find_one({"name_fingerprint": fingerprint})


class DomainRepository(BaseRepository):
    collection_name = "domain_intelligence"

    def cached(self, domain: str, max_age_hours: int = 24) -> dict[str, Any] | None:
        cutoff = utcnow() - timedelta(hours=max_age_hours)
        return self.col.find_one({"domain": domain, "checked_at": {"$gte": cutoff}})

    def upsert(self, domain: str, document: dict[str, Any]) -> dict[str, Any]:
        document["domain"] = domain
        document["checked_at"] = utcnow()
        self.col.update_one({"domain": domain}, {"$set": document}, upsert=True)
        return self.col.find_one({"domain": domain})


class PlanRepository(BaseRepository):
    collection_name = "plans"


class SubscriptionRepository(BaseRepository):
    collection_name = "subscriptions"

    def for_user(self, user_id: str) -> dict[str, Any] | None:
        return self.col.find_one({"user_id": user_id})

    def upsert(self, user_id: str, document: dict[str, Any]) -> dict[str, Any]:
        document["user_id"] = user_id
        document["updated_at"] = utcnow()
        self.col.update_one({"user_id": user_id}, {"$set": document}, upsert=True)
        return self.col.find_one({"user_id": user_id})

    def increment_usage(self, user_id: str, amount: int = 1) -> None:
        self.col.update_one(
            {"user_id": user_id},
            {"$inc": {"scans_used": amount}, "$set": {"updated_at": utcnow()}},
        )


class PaymentRepository(BaseRepository):
    collection_name = "payments"

    def by_event(self, provider_event_id: str) -> dict[str, Any] | None:
        return self.col.find_one({"provider_event_id": provider_event_id})


class ReportRepository(BaseRepository):
    collection_name = "reports"

    def for_analysis(self, analysis_id: str) -> dict[str, Any] | None:
        return self.col.find_one({"analysis_id": analysis_id})

    def upsert(self, analysis_id: str, document: dict[str, Any]) -> dict[str, Any]:
        document["analysis_id"] = analysis_id
        document["updated_at"] = utcnow()
        self.col.update_one({"analysis_id": analysis_id}, {"$set": document}, upsert=True)
        return self.col.find_one({"analysis_id": analysis_id})


class AuditRepository(BaseRepository):
    collection_name = "audit_logs"

    def log(
        self,
        actor_id: str,
        action: str,
        *,
        target: str | None = None,
        metadata: dict[str, Any] | None = None,
        ip: str | None = None,
    ) -> dict[str, Any]:
        return self.insert(
            {
                "actor_id": actor_id,
                "action": action,
                "target": target,
                "metadata": metadata or {},
                "ip": ip,
                "created_at": utcnow(),
            }
        )


class SigninRepository(BaseRepository):
    collection_name = "signin_events"

    def latest(self, user_id: str) -> dict[str, Any] | None:
        return self.col.find_one({"user_id": user_id}, sort=[("created_at", DESCENDING)])

    def for_user(self, user_id: str, limit: int = 10) -> list[dict[str, Any]]:
        return self.find({"user_id": user_id}, sort=[("created_at", DESCENDING)], limit=limit)

    def known_device(self, user_id: str, device_hash: str) -> bool:
        return self.col.find_one({"user_id": user_id, "device_hash": device_hash}) is not None


class ApiUsageRepository(BaseRepository):
    collection_name = "api_usage"

    def increment(self, user_id: str, bucket: str, count: int = 1) -> None:
        self.col.update_one(
            {"user_id": user_id, "bucket": bucket},
            {"$inc": {"count": count}, "$set": {"updated_at": utcnow()}},
            upsert=True,
        )


class ModelRepository(BaseRepository):
    collection_name = "model_registry"

    def active(self, model_name: str) -> dict[str, Any] | None:
        return self.col.find_one({"model_name": model_name, "active": True})

    def register(self, document: dict[str, Any]) -> dict[str, Any]:
        self.col.update_many({"model_name": document["model_name"]}, {"$set": {"active": False}})
        document.setdefault("created_at", utcnow())
        document["active"] = True
        self.col.insert_one(document)
        return document

    def all_versions(self, model_name: str | None = None) -> list[dict[str, Any]]:
        query = {"model_name": model_name} if model_name else {}
        return self.find(query, sort=[("created_at", DESCENDING)], limit=200)


class TaskStatusRepository(BaseRepository):
    collection_name = "task_status"

    def set(self, task_id: str, status: str, **extra: Any) -> dict[str, Any]:
        document = {"task_id": task_id, "status": status, "updated_at": utcnow(), **extra}
        self.col.update_one({"task_id": task_id}, {"$set": document}, upsert=True)
        return self.col.find_one({"task_id": task_id})

    def get(self, task_id: str) -> dict[str, Any] | None:
        return self.col.find_one({"task_id": task_id})


class GenericRepository(BaseRepository):
    def __init__(self, mongo: MongoDBService, collection_name: str) -> None:
        super().__init__(mongo)
        self.collection_name = collection_name


class Repositories:
    """Composition root for all repositories."""

    def __init__(self, mongo: MongoDBService) -> None:
        self.mongo = mongo
        self.users = UserRepository(mongo)
        self.analyses = AnalysisRepository(mongo)
        self.notifications = NotificationRepository(mongo)
        self.monitoring = MonitoringRepository(mongo)
        self.companies = CompanyRepository(mongo)
        self.domains = DomainRepository(mongo)
        self.plans = PlanRepository(mongo)
        self.subscriptions = SubscriptionRepository(mongo)
        self.payments = PaymentRepository(mongo)
        self.reports = ReportRepository(mongo)
        self.audit = AuditRepository(mongo)
        self.api_usage = ApiUsageRepository(mongo)
        self.signins = SigninRepository(mongo)
        self.models = ModelRepository(mongo)
        self.tasks = TaskStatusRepository(mongo)
        self.user_reports = GenericRepository(mongo, "user_reports")
        self.job_listings = GenericRepository(mongo, "job_listings")
        self.url_scans = GenericRepository(mongo, "url_scans")
        self.message_scans = GenericRepository(mongo, "message_scans")
        self.document_scans = GenericRepository(mongo, "document_scans")
        self.risk_indicators = GenericRepository(mongo, "risk_indicators")
        self.processed_events = GenericRepository(mongo, "processed_events")
        self.blacklist = GenericRepository(mongo, "token_blacklist")

    def all(self) -> dict[str, BaseRepository]:
        return {
            name: value
            for name, value in self.__dict__.items()
            if isinstance(value, BaseRepository)
        }
