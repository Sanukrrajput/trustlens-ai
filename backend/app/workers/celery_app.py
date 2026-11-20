"""Celery application, queues, retry policy and beat schedule."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()
use_broker = settings.celery_enabled and bool(settings.redis_url)

celery_app = Celery(
    "hireshield",
    broker=settings.redis_url if use_broker else "memory://",
    backend=settings.redis_url if use_broker else "cache+memory://",
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_always_eager=settings.task_always_eager or not use_broker,
    task_eager_propagates=False,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_retry_delay=30,
    task_max_retries=3,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "collect-monitoring-listings": {
            "task": "app.workers.tasks.run_monitoring",
            "schedule": crontab(minute=f"*/{max(1, settings.monitoring_interval_minutes)}"),
        },
        "refresh-domain-intelligence": {
            "task": "app.workers.tasks.refresh_domain_intelligence",
            "schedule": crontab(minute=0, hour=f"*/{max(1, settings.domain_refresh_interval_hours)}"),
        },
        "aggregate-analytics": {
            "task": "app.workers.tasks.aggregate_analytics",
            "schedule": crontab(minute=0, hour="*/6"),
        },
        "system-health-check": {
            "task": "app.workers.tasks.health_check",
            "schedule": crontab(minute=f"*/{max(1, settings.health_check_interval_minutes)}"),
        },
        "enforce-data-retention": {
            "task": "app.workers.tasks.cleanup_retention",
            "schedule": crontab(minute=0, hour=3),
        },
    },
)


def dispatch_task(name: str, *args, **kwargs) -> str:
    """Enqueue a task when a broker is available; otherwise execute eagerly."""
    result = celery_app.send_task(name, args=args, kwargs=kwargs)
    return str(result.id)
