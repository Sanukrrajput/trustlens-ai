"""FastAPI application factory and service composition root."""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from app.api.deps import require_api_key
from app.alerting.service import AlertService, ResponseActionService
from app.config import Settings, get_settings
from app.correlation.engine import IncidentCorrelator
from app.db.mongo import MongoDBService
from app.db.repositories import Repositories
from app.detection.engine import DetectionEngine
from app.detection.ml import MLDetector, train_models
from app.enrichment.service import EnrichmentService
from app.ingestion.manager import IngestionManager
from app.investigation.assistant import InvestigationAssistant  # noqa: F401 - imported for route availability
from app.logging_conf import configure_logging
from app.scheduler.jobs import JobScheduler
from app.system import SystemHealthService, VERSION
from app.utils import json_safe

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, mongo_client: Any | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    mongo = MongoDBService(settings, client=mongo_client)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        mongo.connect()
        mongo.setup()
        repos = Repositories(mongo)
        app.state.repos = repos

        # Apply operator toggles persisted through the settings API.
        toggles = repos.settings.get("source_toggles", {}) or {}
        if toggles:
            enabled = [
                name
                for name in settings.enabled_sources
                if toggles.get(name, {}).get("enabled", True)
            ]
            for name, config in toggles.items():
                if config.get("enabled") and name not in enabled:
                    enabled.append(name)
            settings.enabled_sources = enabled

        ml = MLDetector(settings, repos)
        ml.ensure_registry()
        ingestion = IngestionManager(settings, mongo, repos)
        detection = DetectionEngine(settings, repos, ml)
        enrichment = EnrichmentService(settings, repos)
        correlator = IncidentCorrelator(settings, repos)
        alerts = AlertService(settings, repos)
        health = SystemHealthService(settings, mongo, repos)
        response = ResponseActionService(settings, repos)
        services: dict[str, Any] = {
            "ingestion": ingestion,
            "detection": detection,
            "enrichment": enrichment,
            "correlator": correlator,
            "alerts": alerts,
            "health": health,
            "response": response,
            "ml": ml,
            "train": lambda: train_models(settings, repos),
        }
        app.state.services = services

        scheduler = JobScheduler(settings, repos, services)
        services["scheduler"] = scheduler
        scheduler.start()

        stop_event = threading.Event()
        stream_thread: threading.Thread | None = None
        if settings.change_stream_enabled and mongo_client is None:
            def on_insert(document: dict[str, Any]) -> None:
                if document:
                    detection.process([document])

            stream_thread = threading.Thread(
                target=mongo.watch_inserts,
                args=("security_events", on_insert, stop_event),
                name="change-stream-listener",
                daemon=True,
            )
            stream_thread.start()

        health.snapshot(scheduler.status())
        logger.info("platform started version=%s environment=%s", VERSION, settings.environment)
        try:
            yield
        finally:
            stop_event.set()
            if stream_thread:
                stream_thread.join(timeout=3)
            scheduler.shutdown()
            mongo.close()

    app = FastAPI(
        title="Intelligent Cybersecurity Threat Intelligence Platform",
        version=VERSION,
        description="Authorized collection, detection, enrichment, risk scoring, correlation and investigation.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.mongo = mongo
    app.state.repos = None
    app.state.services = {}

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(PyMongoError)
    async def mongo_error_handler(request: Request, exc: PyMongoError) -> JSONResponse:
        logger.error("database error path=%s error=%s", request.url.path, exc)
        return JSONResponse(status_code=503, content={"detail": "database temporarily unavailable"})

    @app.get("/health", tags=["system"])
    def health_probe() -> dict[str, Any]:
        return json_safe(mongo.health())

    @app.get("/api/v1/status", tags=["system"], dependencies=[Depends(require_api_key)])
    def status_probe() -> dict[str, Any]:
        services = app.state.services or {}
        return json_safe(
            {
                "version": VERSION,
                "environment": settings.environment,
                "scheduler": services["scheduler"].status() if services.get("scheduler") else {"enabled": False},
                "database": mongo.health(),
            }
        )

    from app.api.routes import admin, core, intel

    app.include_router(core.router, prefix="/api/v1")
    app.include_router(intel.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")

    @app.get("/api/v1", tags=["system"])
    def root() -> dict[str, Any]:
        return {"name": "Threat Intelligence Platform", "version": VERSION, "docs": "/docs"}

    return app


app = create_app()
