"""Shared request/response schemas used by the API, services and frontend."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Role = Literal["user", "student", "staff", "admin", "owner"]
EvidenceStatus = Literal[
    "confirmed_malicious",
    "verified_inconsistency",
    "suspicious",
    "unverified",
    "missing",
    "technical_limitation",
    "supportive",
]


class ORMModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)


class UserRegister(ORMModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=2, max_length=120)
    organisation: str | None = Field(default=None, max_length=160)
    consent_privacy: bool = Field(default=False)
    consent_terms: bool = Field(default=False)

    @field_validator("consent_privacy", "consent_terms")
    @classmethod
    def must_consent(cls, value: bool) -> bool:
        if not value:
            raise ValueError("privacy policy and terms consent are required")
        return value


class UserLogin(ORMModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    # The login form's requested area. It is a routing preference only: the
    # server compares it with the verified account role and never trusts it
    # as a source of privilege.
    access_mode: Literal["user", "admin"] | None = None
    device_id: str | None = Field(default=None, max_length=128)
    remember_device: bool = True
    turnstile_token: str | None = Field(default=None, max_length=4096)


class SigninSummary(ORMModel):
    """The most recent successful sign-in, shown back to the account owner."""

    at: datetime
    device: str
    ip_masked: str | None = None
    country: str | None = None


class SigninEventOut(ORMModel):
    id: str
    at: datetime
    device: str
    ip_masked: str | None = None
    country: str | None = None
    known_device: bool
    verification: str


class LoginSecurityOut(ORMModel):
    enabled: bool
    site_key: str | None = None
    provider: str = "cloudflare_turnstile"
    status: str
    note: str


class TokenPair(ORMModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    device_id: str | None = None
    previous_signin: SigninSummary | None = None
    new_device: bool = False
    verification: str = "not_configured"


class RefreshRequest(ORMModel):
    refresh_token: str


class ForgotPasswordRequest(ORMModel):
    email: EmailStr


class ResetPasswordRequest(ORMModel):
    token: str
    new_password: str = Field(min_length=10, max_length=128)


class VerifyEmailRequest(ORMModel):
    token: str


class UserOut(ORMModel):
    id: str
    email: EmailStr
    full_name: str
    role: Role
    organisation: str | None = None
    email_verified: bool = False
    created_at: datetime
    preferences: dict[str, Any] = Field(default_factory=dict)


class JobAnalysisRequest(ORMModel):
    text: str = Field(min_length=20, max_length=200_000)
    company_name: str | None = Field(default=None, max_length=200)
    job_title: str | None = Field(default=None, max_length=200)
    recruiter_email: EmailStr | None = None
    source_url: str | None = Field(default=None, max_length=2048)
    consent_external_lookups: bool = False
    client_request_id: str | None = Field(default=None, max_length=128)


class MessageAnalysisRequest(ORMModel):
    text: str = Field(min_length=5, max_length=100_000)
    channel: Literal["email", "sms", "whatsapp", "unknown"] = "unknown"
    sender: str | None = Field(default=None, max_length=200)
    consent_external_lookups: bool = False
    client_request_id: str | None = Field(default=None, max_length=128)


class UrlAnalysisRequest(ORMModel):
    url: str = Field(min_length=5, max_length=2048)
    consent_external_lookups: bool = False
    client_request_id: str | None = Field(default=None, max_length=128)


class DocumentAnalysisRequest(ORMModel):
    consent_external_lookups: bool = False
    client_request_id: str | None = Field(default=None, max_length=128)


class CompanyVerifyRequest(ORMModel):
    company_name: str = Field(min_length=2, max_length=200)
    website_url: str | None = Field(default=None, max_length=2048)
    corporate_id: str | None = Field(default=None, max_length=64)
    consent_external_lookups: bool = False
    consent_corporate_registry_lookup: bool = False


class EvidenceIndicator(ORMModel):
    name: str
    status: EvidenceStatus
    severity: float = Field(ge=0.0, le=1.0)
    description: str
    source: str
    reference_url: str | None = None
    observed_at: datetime
    confidence: float = Field(ge=0.0, le=1.0)
    independently_verified: bool = False
    expires_at: datetime | None = None
    weight: float = Field(default=1.0, ge=0.0, le=2.0)


class ModelPrediction(ORMModel):
    model_name: str
    model_version: str
    prediction: str
    fraud_probability: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    contributing_features: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class RiskAssessment(ORMModel):
    score: int = Field(ge=0, le=100)
    category: str
    inconclusive: bool = False
    summary: str
    evidence_summary: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    data_coverage: float = Field(ge=0.0, le=1.0)
    weights_version: str
    component_scores: dict[str, float] = Field(default_factory=dict)


class ExtractedEntities(ORMModel):
    company_names: list[str] = Field(default_factory=list)
    job_titles: list[str] = Field(default_factory=list)
    salary: str | None = None
    recruiter_emails: list[str] = Field(default_factory=list)
    phone_numbers: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    payment_demands: list[str] = Field(default_factory=list)
    sensitive_data_requests: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)


class AnalysisResult(ORMModel):
    id: str
    analysis_type: Literal["job", "message", "url", "document", "monitoring"]
    status: Literal["pending", "completed", "failed"]
    user_id: str
    created_at: datetime
    completed_at: datetime | None = None
    input_preview: str
    extracted: ExtractedEntities = Field(default_factory=ExtractedEntities)
    model_predictions: list[ModelPrediction] = Field(default_factory=list)
    domain_intelligence: dict[str, Any] = Field(default_factory=dict)
    company_intelligence: dict[str, Any] = Field(default_factory=dict)
    message_intelligence: dict[str, Any] = Field(default_factory=dict)
    historical_intelligence: dict[str, Any] = Field(default_factory=dict)
    indicators: list[EvidenceIndicator] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    technical_limitations: list[str] = Field(default_factory=list)
    risk: RiskAssessment
    sources_attempted: list[str] = Field(default_factory=list)
    sources_succeeded: list[str] = Field(default_factory=list)
    report_id: str | None = None


class AnalysisListItem(ORMModel):
    id: str
    analysis_type: str
    created_at: datetime
    status: str
    input_preview: str
    risk_score: int | None = None
    risk_category: str | None = None
    company_name: str | None = None


class Paginated[T: BaseModel](ORMModel):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


class NotificationOut(ORMModel):
    id: str
    user_id: str
    kind: str
    title: str
    body: str
    severity: str
    read: bool
    created_at: datetime
    analysis_id: str | None = None


class MonitoringTaskCreate(ORMModel):
    name: str = Field(min_length=2, max_length=120)
    company_names: list[str] = Field(default_factory=list)
    job_titles: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    enabled: bool = True
    notify_email: bool = True
    notify_in_app: bool = True


class MonitoringTaskOut(ORMModel):
    id: str
    user_id: str
    name: str
    company_names: list[str]
    job_titles: list[str]
    source_urls: list[str]
    keywords: list[str]
    enabled: bool
    notify_email: bool
    notify_in_app: bool
    created_at: datetime
    last_run_at: datetime | None = None
    last_status: str | None = None


class PlanOut(ORMModel):
    code: str
    name: str
    description: str
    price_monthly_paise: int
    price_yearly_paise: int
    currency: str
    scan_limit: int
    features: list[str]
    active: bool = True
    popular: bool = False


class CheckoutRequest(ORMModel):
    plan_code: str
    interval: Literal["monthly", "yearly"] = "monthly"
    provider: Literal["razorpay", "stripe"] = "razorpay"
    success_url: str | None = None
    cancel_url: str | None = None


class CheckoutOut(ORMModel):
    provider: str
    checkout_id: str
    key_id: str | None = None
    checkout_url: str | None = None
    amount: int
    currency: str
    name: str | None = None
    description: str | None = None
    mode: Literal["test", "live", "unknown"] | None = None


class SubscriptionOut(ORMModel):
    id: str
    user_id: str
    plan_code: str
    status: str
    interval: str
    provider: str | None = None
    current_period_end: datetime | None = None
    scans_used: int = 0
    scan_limit: int = 0
    cancel_at_period_end: bool = False


class UserReportCreate(ORMModel):
    analysis_id: str
    report_type: Literal["false_positive", "missed_fraud", "identity_correction", "other"]
    details: str = Field(min_length=10, max_length=5000)
    evidence_url: str | None = None


class UserReportOut(ORMModel):
    id: str
    analysis_id: str
    user_id: str
    report_type: str
    details: str
    status: str
    created_at: datetime


class TaskStatusOut(ORMModel):
    task_id: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
