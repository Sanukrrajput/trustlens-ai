"""Service composition for Celery workers and scheduled jobs."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.core.config import get_settings
from app.db.mongo import MongoDBService
from app.db.repositories import Repositories
from app.services.notification_service import NotificationService
from app.services.plan_service import PlanService


@lru_cache(maxsize=1)
def worker_context() -> dict[str, Any]:
    settings = get_settings()
    mongo = MongoDBService(settings)
    mongo.connect()
    mongo.setup()
    repos = Repositories(mongo)
    plans = PlanService(settings, repos)
    plans.seed()
    return {
        "settings": settings,
        "mongo": mongo,
        "repos": repos,
        "plans": plans,
        "notifications": NotificationService(settings, repos),
    }
