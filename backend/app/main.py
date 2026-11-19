"""HireShield AI API application entrypoint."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from app.api.routes import (
    admin,
    analysis,
    auth,
    billing,
    company,
    monitoring,
    notifications,
    reports,
    system,
)
from app.billing.payments import PaymentConfigurationError
from app.core.config import get_settings
from app.core.logging_conf import configure_logging
from app.core.security import decode_token, hash_password, utcnow, verify_password
from app.db.mongo import MongoDBService
from app.db.repositories import Repositories
from app.services.notification_service import NotificationService
from app.services.plan_service import PlanService

logger = logging.getLogger(__name__)
VERSION = system.VERSION


class LazyCompanyVerifier:
    """Resolve the intelligence service on first use so optional modules fail softly."""

    def __init__(self, settings: Any, repos: Repositories) -> None:
        self.settings = settings
        self.repos = repos
        self._inner: Any | None = None

    def verify(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if self._inner is None:
            from app.intelligence.company_verification.verifier import CompanyVerifier

            self._inner = CompanyVerifier(self.settings, self.repos)
        return self._inner.verify(*args, **kwargs)


def _seed_accounts(settings: Any, repos: Repositories) -> None:
    """Create clearly labelled local demo/admin accounts (development only)."""
    if not settings.seed_demo_data:
        return
    accounts = [
        (settings.demo_email, settings.demo_password, "user", "Demo User", "HireShield Demo"),
        (settings.admin_email, settings.admin_password, "admin", "Platform Admin", "HireShield"),
    ]
    for email, password, role, full_name, organisation in accounts:
        existing = repos.users.get_by_email(email)
        if existing:
            if role == "admin" and existing.get("role") != "admin":
                repos.users.set_role(str(existing["_id"]), "admin")
            continue
        user = repos.users.create(
            {
                "email": email.lower().strip(),
                "password_hash": hash_password(password),
                "full_name": full_name,
                "organisation": organisation,
                "role": role,
                "active": True,
                "email_verified": True,
                "created_at": utcnow(),
                "preferences": {"email_alerts": True, "in_app_alerts": True, "sms_alerts": False},
                "demo_account": True,
            }
        )
        PlanService(settings, repos).ensure_subscription(str(user["_id"]))
        repos.audit.log(str(user["_id"]), "system.demo_account_seeded", target=email)

    demo_user = repos.users.get_by_email(settings.demo_email)
    if not demo_user or repos.analyses.count({"demo_data": True}) >= 2:
        return
    samples = [
        {
            "input_preview": "[DEMO DATA - SYNTHETIC EXAMPLE] Recruiter requests an upfront 'processing fee' and asks for Aadhaar scans via WhatsApp.",
            "risk": {
                "score": 82,
                "category": "High risk",
                "inconclusive": False,
                "summary": "Synthetic demo: fee demand and sensitive-document request are classic recruitment-fraud indicators. Not a real investigation.",
                "evidence_summary": ["Synthetic fee demand", "Sensitive data request via messaging app"],
                "recommended_actions": ["Do not pay any fee", "Verify the employer through an official channel"],
                "confidence": 0.9,
                "data_coverage": 0.4,
                "weights_version": "demo-v1",
                "component_scores": {"rules": 0.8, "message": 0.7},
            },
            "analysis_type": "message",
            "extracted": {"payment_demands": ["processing fee"], "sensitive_data_requests": ["Aadhaar scan"]},
            "indicators": [
                {
                    "name": "demo_upfront_fee",
                    "status": "suspicious",
                    "severity": 0.9,
                    "description": "Synthetic example of an upfront payment demand.",
                    "source": "demo_seed",
                    "observed_at": utcnow(),
                    "confidence": 1.0,
                    "independently_verified": False,
                }
            ],
        },
        {
            "input_preview": "[DEMO DATA - SYNTHETIC EXAMPLE] Well-formed job advertisement from an established employer with an official application portal.",
            "risk": {
                "score": 14,
                "category": "Low observed risk",
                "inconclusive": True,
                "summary": "Synthetic demo: no suspicious indicators in the invented text. External verification was not performed.",
                "evidence_summary": [],
                "recommended_actions": ["Still verify the vacancy on the employer's official careers page"],
                "confidence": 0.35,
                "data_coverage": 0.2,
                "weights_version": "demo-v1",
                "component_scores": {"rules": 0.1},
            },
            "analysis_type": "job",
            "extracted": {},
            "indicators": [],
        },
    ]
    for index, sample in enumerate(samples, start=1):
        repos.analyses.insert(
            {
                **sample,
                "user_id": str(demo_user["_id"]),
                "status": "completed",
                "created_at": utcnow(),
                "completed_at": utcnow(),
                "client_request_id": f"demo-seed-{index}",
                "demo_data": True,
                "demo": True,
                "model_predictions": [],
                "missing_evidence": ["Demo record: no evidence was collected."],
                "technical_limitations": ["Synthetic demo data used for product illustration only."],
                "sources_attempted": [],
                "sources_succeeded": [],
            }
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)
    mongo = MongoDBService(settings)
    in_memory_fallback = False
    try:
        mongo.connect()
        mongo.setup()
    except Exception as exc:  # noqa: BLE001 - explicit fallback for local development only
        if settings.environment.lower() in {"production", "prod"}:
            raise
        logger.warning("MongoDB unavailable (%s); starting with in-memory storage for local development", exc)
        mongo.close()
        fallback_settings = settings.model_copy(update={"mongodb_uri": "mongomock://"})
        mongo = MongoDBService(fallback_settings)
        mongo.setup()
        in_memory_fallback = True

    repos = Repositories(mongo)
    plans = PlanService(settings, repos)
    plans.seed()
    notifications = NotificationService(settings, repos)
    services: dict[str, Any] = {
        "plans": plans,
        "notifications": notifications,
        "company_verifier": LazyCompanyVerifier(settings, repos),
    }

    app.state.settings = settings
    app.state.mongo = mongo
    app.state.repos = repos
    app.state.services = services
    app.state.in_memory_fallback = in_memory_fallback
    app.state.started_at = utcnow()

    try:
        _seed_accounts(settings, repos)
    except Exception as exc:  # noqa: BLE001 - seeding must not prevent startup
        logger.warning("demo account seeding failed: %s", exc)

    logger.info(
        "HireShield AI started environment=%s in_memory_fallback=%s pid=%s",
        settings.environment,
        in_memory_fallback,
        os.getpid(),
    )
    try:
        yield
    finally:
        mongo.close()
        logger.info("HireShield AI stopped")


app = FastAPI(
    title="HireShield AI API",
    version=VERSION,
    description=(
        "Explainable recruitment-fraud detection: ML predictions, consent-gated intelligence, "
        "evidence-backed risk scoring and auditable reports."
    ),
    lifespan=lifespan,
    docs_url="/docs" if get_settings().environment.lower() != "production" else None,
    redoc_url=None,
    openapi_url="/openapi.json" if get_settings().environment.lower() != "production" else None,
)

settings = get_settings()
if "*" not in settings.allowed_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)


@app.middleware("http")
async def security_and_usage_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'")
    if settings.environment.lower() in {"production", "prod"}:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

    if request.url.path.startswith("/api/") and request.url.path != "/api/v1/auth/refresh":
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            try:
                claims = decode_token(settings, authorization.split(" ", 1)[1], expected_type="access")
                repos = getattr(request.app.state, "repos", None)
                if repos is not None:
                    bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H")
                    repos.api_usage.increment(str(claims.get("sub")), bucket)
            except ValueError:
                pass
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = []
    for error in exc.errors():
        location = [str(part) for part in error.get("loc", [])]
        errors.append({"loc": location, "msg": str(error.get("msg", "invalid value"))})
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(PaymentConfigurationError)
async def payment_config_exception_handler(request: Request, exc: PaymentConfigurationError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(PyMongoError)
async def database_exception_handler(request: Request, exc: PyMongoError) -> JSONResponse:
    logger.error("database error path=%s error=%s", request.url.path, exc)
    return JSONResponse(status_code=503, content={"detail": "database temporarily unavailable"})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error path=%s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


API_PREFIX = "/api/v1"
for router in (auth.router, analysis.router, company.router, monitoring.router, reports.router):
    app.include_router(router, prefix=API_PREFIX)
for router in (notifications.router, billing.router, admin.router, system.router):
    app.include_router(router, prefix=API_PREFIX)


@app.get("/", tags=["system"])
def root() -> dict[str, Any]:
    return {
        "service": "HireShield AI",
        "version": VERSION,
        "docs": "/docs" if settings.environment.lower() != "production" else None,
        "api": API_PREFIX,
        "status": "operational",
    }


@app.get("/health", tags=["system"])
def health(request: Request) -> dict[str, Any]:
    mongo = getattr(request.app.state, "mongo", None)
    database = mongo.health() if mongo else {"database": "not_ready"}
    degraded = bool(getattr(request.app.state, "in_memory_fallback", False))
    return {
        "status": "degraded" if degraded else "ok",
        "version": VERSION,
        "environment": settings.environment,
        "database": database,
        "in_memory_fallback": degraded,
        "started_at": getattr(request.app.state, "started_at", None),
    }
