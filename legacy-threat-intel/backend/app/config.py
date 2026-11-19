"""Environment-driven configuration. Secrets are never stored in source code."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: str = "development"
    log_level: str = "INFO"

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "threat_intel"
    api_key: str = ""
    auth_enabled: bool = True
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:3000"])

    scheduler_enabled: bool = True
    change_stream_enabled: bool = True
    collection_interval_minutes: int = 5
    detection_interval_minutes: int = 2
    enrichment_interval_minutes: int = 10
    correlation_interval_minutes: int = 3
    health_interval_minutes: int = 1

    authorized_sources: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["windows_eventlog", "windows_eventlog_file"]
    )
    enabled_sources: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["windows_eventlog", "windows_eventlog_file"]
    )

    windows_eventlog_enabled: bool = True
    windows_eventlog_channels: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["Security", "System", "Microsoft-Windows-PowerShell/Operational"]
    )
    windows_eventlog_event_ids: Annotated[list[int], NoDecode] = Field(
        default_factory=lambda: [4624, 4625, 4672, 4688, 4720, 4723, 4724, 4732, 7045, 4104]
    )
    windows_eventlog_max_events: int = 500
    windows_eventlog_lookback_minutes: int = 10
    windows_eventlog_xml_path: str = ""
    application_log_path: str = ""
    application_log_format: str = "jsonl"
    urlhaus_feed_enabled: bool = False

    ti_enabled: bool = True
    abuseipdb_api_key: str = ""
    urlhaus_api_key: str = ""
    ti_cache_ttl_hours: int = 24
    ti_rate_limit_per_minute: int = 30
    ti_feed_max_records: int = 200

    rule_failed_login_threshold: int = 5
    rule_failure_window_minutes: int = 10
    rule_brute_force_accounts: int = 3
    rule_brute_force_threshold: int = 10
    rule_success_after_failures: int = 3
    rule_success_after_failures_window_minutes: int = 30
    rule_unusual_hours_start: int = 22
    rule_unusual_hours_end: int = 6
    rule_api_rate_threshold: int = 120
    rule_malicious_confidence: float = 0.65
    critical_asset_criticality: int = 4
    ml_min_train_samples: int = 200

    risk_weight_ti: float = 0.30
    risk_weight_ml: float = 0.20
    risk_weight_rule: float = 0.25
    risk_weight_asset: float = 0.15
    risk_weight_correlation: float = 0.10

    correlation_window_hours: int = 24
    event_retention_days: int = 90
    detection_retention_days: int = 90
    incident_retention_days: int = 365
    notification_retention_days: int = 180
    audit_retention_days: int = 365
    job_retention_days: int = 30

    alert_min_severity: str = "high"
    alert_emails: Annotated[list[str], NoDecode] = Field(default_factory=list)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    webhook_url: str = ""
    webhook_secret: str = ""
    response_actions_enabled: bool = False

    model_dir: str = "./models"
    if_contamination: float = 0.05

    @field_validator(
        "cors_origins",
        "authorized_sources",
        "enabled_sources",
        "windows_eventlog_channels",
        "windows_eventlog_event_ids",
        "alert_emails",
        mode="before",
    )
    @classmethod
    def parse_csv(cls, value: Any) -> Any:
        """Accept friendly comma-separated values in .env as well as JSON lists."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def validate_settings(self) -> "Settings":
        if self.auth_enabled and not self.api_key:
            # Development convenience only; production must set API_KEY.
            self.api_key = "development-only-key-change-me"
        if not 0 < self.if_contamination <= 0.5:
            raise ValueError("IF_CONTAMINATION must be in (0, 0.5]")
        return self

    @property
    def risk_weights(self) -> dict[str, float]:
        raw = {
            "threat_intelligence": self.risk_weight_ti,
            "ml_anomaly": self.risk_weight_ml,
            "rule_severity": self.risk_weight_rule,
            "asset_criticality": self.risk_weight_asset,
            "correlation": self.risk_weight_correlation,
        }
        total = sum(max(v, 0.0) for v in raw.values()) or 1.0
        return {k: max(v, 0.0) / total for k, v in raw.items()}

    def public_dict(self) -> dict:
        """Settings safe to display in the UI (no secret values)."""
        secret_fields = {
            "api_key",
            "abuseipdb_api_key",
            "urlhaus_api_key",
            "smtp_password",
            "webhook_secret",
        }
        data = self.model_dump()
        return {
            k: ("***configured***" if v and k in secret_fields else v)
            for k, v in data.items()
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
