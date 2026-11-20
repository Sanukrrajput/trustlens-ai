"""Environment-driven configuration for TrustLens AI.

Secrets are read only from environment variables / .env files and are never written
to source control. External integrations are disabled by default when credentials
are absent; the platform reports that honestly instead of inventing results.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEV_SECRET = "development-only-secret-change-before-launch"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Core
    app_name: str = "TrustLens AI"
    environment: str = "development"
    log_level: str = "INFO"
    secret_key: str = DEV_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    password_reset_expire_minutes: int = 30
    email_verification_expire_hours: int = 24
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"]
    )
    allowed_hosts: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["*"])
    rate_limit_per_minute: int = 120
    rate_limit_window_seconds: int = 60

    # Login verification. Turnstile activates only when both keys are supplied;
    # unconfigured deployments report "not_configured" instead of simulating a check.
    turnstile_enabled: bool = True
    turnstile_site_key: str = ""
    turnstile_secret_key: str = ""
    turnstile_expected_hostname: str = ""

    # Local demo/admin seeding. Disabled automatically in production unless strong
    # credentials are explicitly supplied through the environment.
    seed_demo_data: bool = True
    demo_email: str = "demo@hireshield.io"
    demo_password: str = "DemoPass123!"
    admin_email: str = "admin@hireshield.io"
    admin_password: str = "AdminPass123!"

    # Persistence and automation
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "hireshield"
    redis_url: str = "redis://localhost:6379/0"
    celery_enabled: bool = True
    task_always_eager: bool = False
    scheduler_enabled: bool = True
    monitoring_interval_minutes: int = 60
    domain_refresh_interval_hours: int = 24
    health_check_interval_minutes: int = 5
    retention_days: int = 365
    audit_retention_days: int = 730
    retention_enabled: bool = True

    # Storage and uploads
    model_dir: str = "./models"
    data_dir: str = "./data"
    max_upload_mb: int = 10
    allowed_upload_mime: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "application/pdf",
            "image/png",
            "image/jpeg",
            "image/webp",
            "text/plain",
        ]
    )
    max_fetch_bytes: int = 262_144
    fetch_timeout_seconds: float = 8.0
    max_redirects: int = 4

    # Optional external intelligence. Empty values mean "not configured".
    virustotal_api_key: str = ""
    google_safebrowsing_api_key: str = ""
    google_webrisk_api_key: str = ""
    mca_api_url: str = ""
    mca_api_key: str = ""
    mca_require_consent: bool = True
    rdap_enabled: bool = True
    dns_enabled: bool = True
    tls_enabled: bool = True

    # Approved job-source adapters. Only URLs explicitly listed here are queried.
    job_source_urls: Annotated[list[str], NoDecode] = Field(default_factory=list)
    job_source_api_keys: Annotated[list[str], NoDecode] = Field(default_factory=list)
    job_source_max_per_run: int = 100

    # Notifications
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "TrustLens AI <no-reply@trustlens.local>"
    smtp_use_tls: bool = True
    sms_provider_url: str = ""
    sms_provider_api_key: str = ""
    sms_sender_id: str = "TrustLens"
    notify_email_on_high_risk: bool = True

    # Billing. Prices are configurable through the plans collection / admin API.
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    payment_currency: str = "INR"

    # Explainable signal weights (normalised to 1.0 at runtime). These are the
    # specification's initial split: content 30%, URL/domain 25%, brand/identity
    # 25%, threat indicators 10% and community/history 10%. Legacy
    # RISK_WEIGHT_ML/RULES/DOMAIN/COMPANY/HISTORY/MESSAGE variables are no
    # longer read; use the five names below.
    risk_weight_content: float = 0.30
    risk_weight_url: float = 0.25
    risk_weight_brand: float = 0.25
    risk_weight_threat: float = 0.10
    risk_weight_community: float = 0.10

    # Score band upper bounds, configurable without a code change.
    risk_band_low_max: int = 19
    risk_band_limited_max: int = 39
    risk_band_moderate_max: int = 59
    risk_band_high_max: int = 79

    # Default free-plan limits; admin-configurable plans override these.
    free_scan_limit: int = 10
    student_scan_limit: int = 100
    professional_scan_limit: int = 500
    university_scan_limit: int = 5000
    enterprise_scan_limit: int = 100_000

    @field_validator(
        "cors_origins",
        "allowed_hosts",
        "allowed_upload_mime",
        "job_source_urls",
        "job_source_api_keys",
        mode="before",
    )
    @classmethod
    def parse_csv(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.environment.lower() in {"production", "prod"} and self.secret_key == DEV_SECRET:
            raise ValueError("SECRET_KEY must be set to a strong random value in production")
        if self.monitoring_interval_minutes < 1:
            raise ValueError("MONITORING_INTERVAL_MINUTES must be >= 1")
        if self.rate_limit_per_minute < 1:
            raise ValueError("RATE_LIMIT_PER_MINUTE must be >= 1")
        if self.rate_limit_window_seconds < 1:
            raise ValueError("RATE_LIMIT_WINDOW_SECONDS must be >= 1")
        if self.retention_days < 1 or self.audit_retention_days < 1:
            raise ValueError("RETENTION_DAYS and AUDIT_RETENTION_DAYS must be >= 1")
        bounds = (
            self.risk_band_low_max,
            self.risk_band_limited_max,
            self.risk_band_moderate_max,
            self.risk_band_high_max,
        )
        if any(not 0 <= value <= 100 for value in bounds) or sorted(bounds) != list(bounds):
            raise ValueError("Risk score band bounds must be ordered and between 0 and 100")
        if self.environment.lower() in {"production", "prod"} and self.seed_demo_data:
            weak_defaults = {
                "DemoPass123!",
                "AdminPass123!",
                "development-only-secret-change-before-launch",
            }
            if self.demo_password in weak_defaults or self.admin_password in weak_defaults:
                # Never create predictable accounts in a production deployment.
                self.seed_demo_data = False
        return self

    @property
    def turnstile_active(self) -> bool:
        """True only when Turnstile can actually be verified server-side."""
        return self.turnstile_enabled and bool(self.turnstile_site_key and self.turnstile_secret_key)

    @property
    def risk_weights(self) -> dict[str, float]:
        raw = {
            "content": self.risk_weight_content,
            "url": self.risk_weight_url,
            "brand": self.risk_weight_brand,
            "threat": self.risk_weight_threat,
            "community": self.risk_weight_community,
        }
        defaults = {
            "content": 0.30,
            "url": 0.25,
            "brand": 0.25,
            "threat": 0.10,
            "community": 0.10,
        }
        cleaned = {key: max(0.0, value) if value >= 0 else defaults[key] for key, value in raw.items()}
        total = sum(cleaned.values()) or 1.0
        return {key: value / total for key, value in cleaned.items()}

    @property
    def risk_bands(self) -> tuple[int, int, int, int]:
        """Upper bounds for low, limited, moderate and high risk bands."""
        return (
            self.risk_band_low_max,
            self.risk_band_limited_max,
            self.risk_band_moderate_max,
            self.risk_band_high_max,
        )

    def public_dict(self) -> dict[str, Any]:
        """Return non-secret configuration for the admin UI."""
        secrets = {
            "secret_key",
            "virustotal_api_key",
            "google_safebrowsing_api_key",
            "google_webrisk_api_key",
            "mca_api_key",
            "smtp_password",
            "sms_provider_api_key",
            "razorpay_key_secret",
            "razorpay_webhook_secret",
            "stripe_secret_key",
            "stripe_webhook_secret",
            "turnstile_secret_key",
        }
        return {
            key: ("***configured***" if value and key in secrets else value)
            for key, value in self.model_dump().items()
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# Backwards-compatible dependency alias used by the API route modules.
get_app_settings = get_settings
