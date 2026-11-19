"""Pydantic schemas for normalization and API input validation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils import parse_ts, redact


class NormalizedEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    event_id: str
    source_type: str
    source_name: str = ""
    source_id: str = ""
    host: str = ""
    event_type: str
    event_action: str = ""
    timestamp: datetime
    actor_user: str | None = None
    actor_domain: str | None = None
    source_ip: str | None = None
    destination_ip: str | None = None
    destination_port: int | None = None
    protocol: str | None = None
    destination_host: str | None = None
    url: str | None = None
    domain: str | None = None
    file_hash: str | None = None
    process_name: str | None = None
    command_line: str | None = None
    asset_id: str | None = None
    asset_criticality: int = 0
    message: str = ""
    raw: str = ""
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    indicators: list[dict[str, str]] = Field(default_factory=list)
    dedupe_key: str
    label: str | None = None

    @field_validator("timestamp", mode="before")
    @classmethod
    def coerce_timestamp(cls, value: Any) -> datetime:
        return parse_ts(value)

    @field_validator("raw", mode="before")
    @classmethod
    def clean_raw(cls, value: Any) -> str:
        return redact(value if isinstance(value, str) else str(value or ""))

    @field_validator("actor_user", "destination_host", "host", mode="before")
    @classmethod
    def clean_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        return str(value)[:256]


class IndicatorInput(BaseModel):
    type: Literal["ip", "ipv4", "ipv6", "domain", "url", "hash", "md5", "sha1", "sha256"]
    value: str = Field(min_length=1, max_length=2048)


class AssetInput(BaseModel):
    asset_id: str = Field(min_length=1, max_length=128)
    hostname: str = ""
    ip_addresses: list[str] = Field(default_factory=list)
    criticality: int = Field(default=1, ge=0, le=5)
    owner: str = ""
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True


class FeedbackInput(BaseModel):
    detection_id: str
    verdict: Literal["true_positive", "false_positive", "benign", "malicious"]
    analyst: str = "analyst"
    note: str = ""
    label: Literal["malicious", "benign"] | None = None


class SettingsUpdate(BaseModel):
    overrides: dict[str, Any] = Field(default_factory=dict)

    @field_validator("overrides")
    @classmethod
    def validate_keys(cls, value: dict[str, Any]) -> dict[str, Any]:
        allowed_prefixes = (
            "rule_", "risk_weight_", "correlation_", "alert_", "critical_asset_", "ml_", "ti_"
        )
        unknown = [k for k in value if not k.startswith(allowed_prefixes)]
        if unknown:
            raise ValueError(f"settings not editable at runtime: {', '.join(unknown)}")
        return value


class IncidentStatusUpdate(BaseModel):
    status: Literal["new", "investigating", "contained", "resolved", "closed", "false_positive"]
    note: str = ""


class ResponseActionInput(BaseModel):
    incident_id: str
    action_type: Literal["block_ip", "disable_account", "isolate_asset", "reset_credentials", "custom"]
    target: str = Field(min_length=1, max_length=256)
    rationale: str = ""
    requested_by: str = "analyst"


class SourceToggle(BaseModel):
    enabled: bool
    authorized: bool | None = None
