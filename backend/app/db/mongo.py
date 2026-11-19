"""MongoDB connection, collection bootstrap, indexes, validation and retention."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, DESCENDING, IndexModel, MongoClient
from pymongo.errors import CollectionInvalid, OperationFailure, PyMongoError

from app.core.config import Settings

logger = logging.getLogger(__name__)

COLLECTIONS = [
    "users",
    "organizations",
    "subscriptions",
    "payments",
    "job_listings",
    "companies",
    "recruiters",
    "domain_intelligence",
    "url_scans",
    "message_scans",
    "document_scans",
    "fraud_analyses",
    "risk_indicators",
    "notifications",
    "monitoring_tasks",
    "user_reports",
    "model_registry",
    "model_evaluations",
    "audit_logs",
    "api_usage",
    "plans",
    "task_status",
    "processed_events",
    "platform_settings",
    "reports",
    "password_resets",
    "token_blacklist",
    "health_checks",
    "signin_events",
    "support_messages",
]

# Lightweight validators: strict enough to catch malformed documents, permissive
# enough to allow service-owned nested structures to evolve.
VALIDATORS: dict[str, dict[str, Any]] = {
    "users": {
        "bsonType": "object",
        "required": ["email", "password_hash", "role", "created_at"],
        "properties": {
            "email": {"bsonType": "string"},
            "password_hash": {"bsonType": "string"},
            "role": {"enum": ["user", "student", "staff", "admin", "owner"]},
            "created_at": {"bsonType": "date"},
        },
    },
    "fraud_analyses": {
        "bsonType": "object",
        "required": ["user_id", "analysis_type", "status", "created_at", "risk"],
        "properties": {
            "user_id": {"bsonType": "string"},
            "analysis_type": {"bsonType": "string"},
            "status": {"bsonType": "string"},
            "created_at": {"bsonType": "date"},
            "risk": {"bsonType": "object"},
        },
    },
    "notifications": {
        "bsonType": "object",
        "required": ["user_id", "kind", "title", "created_at"],
        "properties": {
            "user_id": {"bsonType": "string"},
            "kind": {"bsonType": "string"},
            "title": {"bsonType": "string"},
            "created_at": {"bsonType": "date"},
        },
    },
    "audit_logs": {
        "bsonType": "object",
        "required": ["actor_id", "action", "created_at"],
        "properties": {
            "actor_id": {"bsonType": "string"},
            "action": {"bsonType": "string"},
            "created_at": {"bsonType": "date"},
        },
    },
    "signin_events": {
        "bsonType": "object",
        "required": ["user_id", "created_at", "verification"],
        "properties": {
            "user_id": {"bsonType": "string"},
            "created_at": {"bsonType": "date"},
            "verification": {"bsonType": "string"},
        },
    },
    "support_messages": {
        "bsonType": "object",
        "required": ["session_id", "role", "text", "created_at"],
        "properties": {
            "session_id": {"bsonType": "string"},
            "role": {"enum": ["user", "assistant"]},
            "text": {"bsonType": "string"},
            "created_at": {"bsonType": "date"},
        },
    },
}

INDEXES: dict[str, list[IndexModel]] = {
    "users": [
        IndexModel([("email", ASCENDING)], unique=True, name="uniq_email"),
        IndexModel([("created_at", DESCENDING)], name="created_at_desc"),
    ],
    "fraud_analyses": [
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_created"),
        IndexModel([("risk.score", DESCENDING)], name="risk_score"),
        IndexModel([("analysis_type", ASCENDING)], name="analysis_type"),
        IndexModel([("extracted.company_fingerprint", ASCENDING)], name="company_fp"),
        IndexModel([("client_request_id", ASCENDING), ("user_id", ASCENDING)], unique=True, sparse=True, name="uniq_idempotency"),
        IndexModel([("created_at", ASCENDING)], name="analysis_ttl", expireAfterSeconds=365 * 24 * 3600),
    ],
    "notifications": [
        IndexModel([("user_id", ASCENDING), ("read", ASCENDING), ("created_at", DESCENDING)], name="user_unread"),
        IndexModel([("dedupe_key", ASCENDING)], unique=True, sparse=True, name="uniq_dedupe"),
        IndexModel([("created_at", ASCENDING)], name="notification_ttl", expireAfterSeconds=180 * 24 * 3600),
    ],
    "monitoring_tasks": [
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_created"),
    ],
    "domain_intelligence": [
        IndexModel([("domain", ASCENDING)], unique=True, name="uniq_domain"),
        IndexModel([("checked_at", ASCENDING)], name="cache_ttl", expireAfterSeconds=30 * 24 * 3600),
    ],
    "companies": [
        IndexModel([("name_fingerprint", ASCENDING)], unique=True, name="uniq_company_fp"),
        IndexModel([("domain", ASCENDING)], name="domain"),
    ],
    "job_listings": [
        IndexModel([("fingerprint", ASCENDING)], unique=True, name="uniq_listing_fp"),
        IndexModel([("published_at", DESCENDING)], name="published_desc"),
    ],
    "subscriptions": [
        IndexModel([("user_id", ASCENDING)], unique=True, name="uniq_user_sub"),
    ],
    "payments": [
        IndexModel([("provider_payment_id", ASCENDING)], unique=True, sparse=True, name="uniq_payment"),
        IndexModel([("provider_event_id", ASCENDING)], unique=True, sparse=True, name="uniq_event"),
    ],
    "user_reports": [
        IndexModel([("analysis_id", ASCENDING), ("user_id", ASCENDING)], name="analysis_user"),
    ],
    "api_usage": [
        IndexModel([("user_id", ASCENDING), ("bucket", ASCENDING)], unique=True, name="uniq_usage_bucket"),
    ],
    "audit_logs": [
        IndexModel([("actor_id", ASCENDING), ("created_at", DESCENDING)], name="actor_created"),
        IndexModel([("created_at", ASCENDING)], name="audit_ttl", expireAfterSeconds=730 * 24 * 3600),
    ],
    "model_registry": [
        IndexModel([("model_name", ASCENDING), ("version", ASCENDING)], unique=True, name="uniq_model_version"),
    ],
    "task_status": [
        IndexModel([("task_id", ASCENDING)], unique=True, name="uniq_task"),
        IndexModel([("created_at", ASCENDING)], name="task_ttl", expireAfterSeconds=7 * 24 * 3600),
    ],
    "processed_events": [
        IndexModel([("event_id", ASCENDING)], unique=True, name="uniq_event"),
    ],
    "support_messages": [
        IndexModel([("session_id", ASCENDING), ("created_at", ASCENDING)], name="session_created"),
        IndexModel([("created_at", ASCENDING)], name="support_ttl", expireAfterSeconds=30 * 24 * 3600),
    ],
    "signin_events": [
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_created"),
        IndexModel([("user_id", ASCENDING), ("device_hash", ASCENDING)], name="user_device"),
        IndexModel([("created_at", ASCENDING)], name="signin_ttl", expireAfterSeconds=365 * 24 * 3600),
    ],
    "reports": [
        IndexModel([("analysis_id", ASCENDING)], unique=True, name="uniq_analysis_report"),
    ],
}


class MongoDBService:
    """Owns the Mongo client and ensures the platform's data contracts exist."""

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self.settings = settings
        self._external_client = client is not None
        if client is not None:
            self.client = client
        elif settings.mongodb_uri.startswith("mongomock://"):
            import mongomock

            self.client = mongomock.MongoClient()
        else:
            self.client = MongoClient(
                settings.mongodb_uri,
                serverSelectionTimeoutMS=5000,
                maxPoolSize=20,
                tz_aware=True,
            )
        self.db = self.client[settings.mongodb_db]

    def connect(self) -> None:
        # PyMongo connects lazily; this forces an early, observable failure.
        self.client.admin.command("ping")

    def setup(self) -> None:
        existing = set(self.db.list_collection_names())
        for name in COLLECTIONS:
            if name in existing:
                continue
            options: dict[str, Any] = {}
            validator = VALIDATORS.get(name)
            if validator and not self._is_mongomock():
                options["validator"] = {"$jsonSchema": validator}
                options["validationLevel"] = "moderate"
            try:
                self.db.create_collection(name, **options)
            except CollectionInvalid:
                pass
            except OperationFailure as exc:
                logger.warning("could not apply schema validation to %s: %s", name, exc)
        for name, indexes in INDEXES.items():
            try:
                self.db[name].create_indexes(indexes)
            except (OperationFailure, PyMongoError) as exc:
                logger.warning("could not create indexes for %s: %s", name, exc)

    def collection(self, name: str):
        if name not in COLLECTIONS:
            raise KeyError(f"unknown collection: {name}")
        return self.db[name]

    def health(self) -> dict[str, Any]:
        try:
            self.client.admin.command("ping")
            return {"database": "connected", "name": self.settings.mongodb_db, "collections": len(COLLECTIONS)}
        except PyMongoError as exc:
            return {"database": "unavailable", "error": str(exc)}

    def close(self) -> None:
        if not self._external_client:
            self.client.close()

    def _is_mongomock(self) -> bool:
        return self.settings.mongodb_uri.startswith("mongomock://") or self._external_client
