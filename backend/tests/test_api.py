"""End-to-end API integration tests using an isolated in-memory database."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from typing import Any

os.environ["MONGODB_URI"] = "mongomock://"
os.environ["CELERY_ENABLED"] = "false"
os.environ["TASK_ALWAYS_EAGER"] = "true"
os.environ["SEED_DEMO_DATA"] = "true"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.repositories import AnalysisRepository  # noqa: E402

BASE = "/api/v1"


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _register(client: TestClient, email: str | None = None, password: str = "StrongPass123!") -> dict:
    payload = {
        "email": email or f"user-{uuid.uuid4().hex[:10]}@example.com",
        "password": password,
        "full_name": "Integration Tester",
        "organisation": "Test Org",
        "consent_privacy": True,
        "consent_terms": True,
    }
    response = client.post(f"{BASE}/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return payload


def _login(client: TestClient, email: str, password: str = "StrongPass123!") -> dict[str, str]:
    response = client.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    tokens = response.json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _auth_client(client: TestClient) -> tuple[dict[str, str], str]:
    credentials = _register(client)
    return _login(client, credentials["email"]), credentials["email"]


def test_pending_analysis_satisfies_mongo_validator(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """The initial insert must include every field required by the real Mongo validator.

    mongomock skips $jsonSchema validation, so this check enforces the required
    keys explicitly and prevents the pending document from causing a 503 on a
    real MongoDB deployment.
    """
    required = {"user_id", "analysis_type", "status", "created_at", "risk"}
    original_insert = AnalysisRepository.insert

    def validating_insert(self: AnalysisRepository, document: dict) -> dict:
        missing = required.difference(document)
        assert not missing, f"pending analysis is missing required fields: {sorted(missing)}"
        return original_insert(self, document)

    monkeypatch.setattr(AnalysisRepository, "insert", validating_insert)

    headers, _ = _auth_client(client)
    response = client.post(
        f"{BASE}/analysis/url",
        headers=headers,
        json={"url": "https://example.com/careers/job", "consent_external_lookups": False},
    )
    assert response.status_code == 200, response.text
    assert response.json()["risk"]["category"] != "pending"


def test_url_analysis_handles_provenance_wrapped_domain_age(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Domain facts are wrapped with provenance, not raw numeric values."""
    from app.intelligence.domain_analysis.analyser import DomainAnalyser
    from app.intelligence.url_scanning.safe_fetch import SafeURLFetcher

    monkeypatch.setattr(
        SafeURLFetcher,
        "fetch",
        lambda self, url: {"status": "ok", "final_url": url, "errors": [], "limitations": []},
    )
    monkeypatch.setattr(
        DomainAnalyser,
        "analyse",
        lambda self, url, refresh=False: {
            "status": "ok",
            "indicators": [],
            "signals": {
                "domain_age_days": {"value": 120, "source": "RDAP", "confidence": 0.8},
            },
        },
    )

    headers, _ = _auth_client(client)
    response = client.post(
        f"{BASE}/analysis/url",
        headers=headers,
        json={"url": "https://example.com/careers/job", "consent_external_lookups": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert body["domain_intelligence"]["signals"]["domain_age_days"]["value"] == 120
    assert any(item["model_name"] == "anomaly_rule_fallback" for item in body["model_predictions"])


def test_completed_report_contains_structured_evidence_fields(client: TestClient) -> None:
    headers, _ = _auth_client(client)
    response = client.post(
        f"{BASE}/analysis/offer",
        headers=headers,
        json={
            "text": (
                "LIMITED OFFER: transfer INR 2000 now to claim your scholarship grant and send "
                "your bank OTP to the organiser before the offer expires today."
            ),
            "offer_category": "scholarship",
            "company_name": "Example Foundation",
            "consent_external_lookups": False,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    risk = body["risk"]

    assert set(risk["signal_weights"]) == {"content", "url", "brand", "threat", "community"}
    assert isinstance(risk["uncertainty"], (int, float))
    assert 0.0 <= risk["uncertainty"] <= 1.0
    assert isinstance(risk["unavailable_signals"], list)
    assert risk["recommended_actions"]
    assert body["evidence_collected_at"]
    assert body["evidence_sources"]
    for source in body["evidence_sources"]:
        assert {"name", "status", "attempted_at", "observed_at"} <= set(source)
    assert body["missing_evidence"]

    pdf = client.get(f"{BASE}/reports/{body['id']}/pdf", headers=headers)
    assert pdf.status_code == 200, pdf.text
    assert pdf.content.startswith(b"%PDF")


def test_health_public_config_and_security_headers(client: TestClient) -> None:
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] in {"ok", "degraded"}
    assert client.get(f"{BASE}/health").status_code == 200

    config = client.get(f"{BASE}/system/config").json()
    assert config["app_name"] == "TrustLens AI"
    assert isinstance(config["integrations"], dict)
    assert config["features"]["webhook_only_payment_activation"] is True
    assert "secret_key" not in json.dumps(config)
    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.headers["x-frame-options"] == "DENY"


def test_auth_lifecycle(client: TestClient) -> None:
    credentials = _register(client)
    tokens = client.post(
        f"{BASE}/auth/login",
        json={"email": credentials["email"], "password": credentials["password"]},
    ).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    me = client.get(f"{BASE}/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == credentials["email"]

    refreshed = client.post(f"{BASE}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]

    logout = client.post(f"{BASE}/auth/logout", headers=headers)
    assert logout.status_code == 200
    assert client.get(f"{BASE}/auth/me", headers=headers).status_code == 401


def test_job_analysis_persistence_report_and_feedback(client: TestClient) -> None:
    headers, _ = _auth_client(client)
    response = client.post(
        f"{BASE}/analysis/job",
        headers=headers,
        json={
            "text": (
                "URGENT hiring! No interview required. Pay a registration charge of INR 5000 "
                "and share your OTP and Aadhaar scan to secure this work from home job immediately."
            ),
            "company_name": "Example Recruitment Services",
            "job_title": "Data Entry Operator",
            "consent_external_lookups": False,
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "completed"
    assert 0 <= result["risk"]["score"] <= 100
    assert result["risk"]["weights_version"]
    assert isinstance(result["indicators"], list)
    assert result["model_predictions"]
    assert any("no URL or domain" in reason or "consent" in reason for reason in [result["domain_intelligence"].get("reason", "")])

    listed = client.get(f"{BASE}/analysis", headers=headers).json()
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == result["id"]

    fetched = client.get(f"{BASE}/analysis/{result['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["extracted"]

    report = client.get(f"{BASE}/reports/{result['id']}", headers=headers)
    assert report.status_code == 200
    pdf = client.get(f"{BASE}/reports/{result['id']}/pdf", headers=headers)
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")

    feedback = client.post(
        f"{BASE}/reports/feedback",
        headers=headers,
        json={
            "analysis_id": result["id"],
            "report_type": "false_positive",
            "details": "This was an actual verified employer advertisement.",
        },
    )
    assert feedback.status_code == 200, feedback.text
    assert feedback.json()["status"] == "pending_review"


def test_message_and_url_analysis_without_consent(client: TestClient) -> None:
    headers, _ = _auth_client(client)
    message = client.post(
        f"{BASE}/analysis/message",
        headers=headers,
        json={
            "text": "Congratulations! Send a processing fee and your bank OTP to confirm the offer.",
            "channel": "whatsapp",
            "sender": "+919876543210",
            "consent_external_lookups": False,
        },
    )
    assert message.status_code == 200, message.text
    assert message.json()["analysis_type"] == "message"

    url = client.post(
        f"{BASE}/analysis/url",
        headers=headers,
        json={"url": "https://example.com/careers/apply", "consent_external_lookups": False},
    )
    assert url.status_code == 200, url.text
    risk = url.json()["risk"]
    assert isinstance(risk["inconclusive"], bool)
    assert 0 <= risk["score"] <= 100


def test_billing_plans_subscription_and_unconfigured_checkout(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A local .env may contain real test keys; this test deliberately clears them
    # so the fail-closed behaviour stays deterministic in every environment.
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_key_id", "")
    monkeypatch.setattr(settings, "razorpay_key_secret", "")

    headers, _ = _auth_client(client)
    plans = client.get(f"{BASE}/billing/plans").json()
    assert {plan["code"] for plan in plans} >= {"free", "student", "professional"}

    subscription = client.get(f"{BASE}/billing/subscription", headers=headers).json()
    assert subscription["plan_code"] == "free"
    assert subscription["scans_used"] == 0

    checkout = client.post(
        f"{BASE}/billing/checkout",
        headers=headers,
        json={"plan_code": "professional", "interval": "monthly", "provider": "razorpay"},
    )
    assert checkout.status_code == 503
    assert "not configured" in checkout.json()["detail"].lower()


def test_razorpay_checkout_creates_order_with_server_notes(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_local_key")
    monkeypatch.setattr(settings, "razorpay_key_secret", "local-secret")

    headers, _ = _auth_client(client)
    user_id = client.get(f"{BASE}/auth/me", headers=headers).json()["id"]
    captured: dict[str, Any] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"id": "order_test_1", "amount": 29900, "currency": "INR", "status": "created"}

    def fake_post(url: str, **kwargs: Any) -> FakeResponse:
        captured["url"] = url
        captured["kwargs"] = kwargs
        return FakeResponse()

    monkeypatch.setattr("app.billing.payments.requests.post", fake_post)
    response = client.post(
        f"{BASE}/billing/checkout",
        headers=headers,
        json={"plan_code": "professional", "interval": "monthly", "provider": "razorpay"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["checkout_id"] == "order_test_1"
    assert body["key_id"] == "rzp_test_local_key"
    assert body["mode"] == "test"
    assert body["name"] == "TrustLens AI — Professional"
    assert captured["url"] == "https://api.razorpay.com/v1/orders"
    assert captured["kwargs"]["auth"] == ("rzp_test_local_key", "local-secret")
    assert captured["kwargs"]["json"]["amount"] == 29900
    assert captured["kwargs"]["json"]["notes"]["user_id"] == user_id
    assert captured["kwargs"]["json"]["notes"]["plan_code"] == "professional"
    assert captured["kwargs"]["json"]["notes"]["interval"] == "monthly"


def test_razorpay_webhook_uses_order_notes_and_rejects_amount_mismatch(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_webhook_secret", "order-notes-secret")
    headers, _ = _auth_client(client)
    user_id = client.get(f"{BASE}/auth/me", headers=headers).json()["id"]

    def signed_post(event: dict[str, Any]) -> Any:
        body = json.dumps(event).encode()
        signature = hmac.new(settings.razorpay_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        return client.post(
            f"{BASE}/billing/webhooks/razorpay",
            content=body,
            headers={"Content-Type": "application/json", "X-Razorpay-Signature": signature},
        )

    captured_event = {
        "id": "evt_order_notes_1",
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {"id": "pay_1", "amount": 29900, "currency": "INR", "order_id": "order_1"}
            },
            "order": {
                "entity": {
                    "id": "order_1",
                    "notes": {"user_id": user_id, "plan_code": "professional", "interval": "monthly"},
                }
            },
        },
    }
    verified = signed_post(captured_event)
    assert verified.status_code == 200, verified.text
    assert verified.json()["subscription_status"] == "active"
    subscription = client.get(f"{BASE}/billing/subscription", headers=headers).json()
    assert subscription["plan_code"] == "professional"
    assert subscription["provider"] == "razorpay"

    mismatch = {
        "id": "evt_order_notes_2",
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {"id": "pay_2", "amount": 100, "currency": "INR", "order_id": "order_2"}
            },
            "order": {
                "entity": {
                    "id": "order_2",
                    "notes": {"user_id": user_id, "plan_code": "professional", "interval": "monthly"},
                }
            },
        },
    }
    rejected = signed_post(mismatch)
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["subscription_status"] == "amount_mismatch"
    subscription = client.get(f"{BASE}/billing/subscription", headers=headers).json()
    assert subscription["plan_code"] == "professional"


def test_only_verified_webhook_can_activate_paid_plan(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers, email = _auth_client(client)
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_webhook_secret", "integration-test-secret")
    user_id = client.get(f"{BASE}/auth/me", headers=headers).json()["id"]

    unsigned = client.post(f"{BASE}/billing/webhooks/razorpay", json={"event": "payment.captured"})
    assert unsigned.status_code == 400

    event = {
        "id": "evt_integration_1",
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_integration_1",
                    "notes": {"user_id": user_id, "plan_code": "professional", "interval": "monthly"},
                }
            }
        },
    }
    body = json.dumps(event).encode()
    signature = hmac.new(settings.razorpay_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    verified = client.post(
        f"{BASE}/billing/webhooks/razorpay",
        content=body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": signature},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["status"] == "processed"

    subscription = client.get(f"{BASE}/billing/subscription", headers=headers).json()
    assert subscription["plan_code"] == "professional"
    assert subscription["provider"] == "razorpay"
    assert email  # keep the test focused on payment state transitions


def test_rbac_admin_endpoints(client: TestClient) -> None:
    user_headers, _ = _auth_client(client)
    assert client.get(f"{BASE}/admin/dashboard", headers=user_headers).status_code == 403

    admin_headers = _login(client, "admin@hireshield.io", "AdminPass123!")
    dashboard = client.get(f"{BASE}/admin/dashboard", headers=admin_headers)
    assert dashboard.status_code == 200, dashboard.text
    data = dashboard.json()
    assert data["total_users"] >= 2
    assert isinstance(data["scans_by_type"], list)
    for path in ("users", "models", "reports", "audit-logs", "plans", "tasks", "config"):
        response = client.get(f"{BASE}/admin/{path}", headers=admin_headers)
        assert response.status_code == 200, (path, response.text)


def test_login_access_mode_is_checked_against_verified_role(client: TestClient) -> None:
    credentials = _register(client)

    as_admin = client.post(
        f"{BASE}/auth/login",
        json={**credentials, "access_mode": "admin"},
    )
    assert as_admin.status_code == 403
    assert "administrator" in as_admin.json()["detail"]

    as_user = client.post(f"{BASE}/auth/login", json={**credentials, "access_mode": "user"})
    assert as_user.status_code == 200

    admin_as_user = client.post(
        f"{BASE}/auth/login",
        json={
            "email": "admin@hireshield.io",
            "password": "AdminPass123!",
            "access_mode": "user",
        },
    )
    assert admin_as_user.status_code == 403
    assert "administrator" in admin_as_user.json()["detail"].lower()

    admin_as_admin = client.post(
        f"{BASE}/auth/login",
        json={
            "email": "admin@hireshield.io",
            "password": "AdminPass123!",
            "access_mode": "admin",
        },
    )
    assert admin_as_admin.status_code == 200
    assert admin_as_admin.json()["access_token"]


def test_admin_can_create_user_and_admin_accounts(client: TestClient) -> None:
    admin_headers = _login(client, "admin@hireshield.io", "AdminPass123!")
    user_headers, _ = _auth_client(client)

    forbidden = client.post(
        f"{BASE}/admin/users",
        headers=user_headers,
        json={
            "email": "not-allowed@example.com",
            "password": "StrongPass123!",
            "full_name": "Not Allowed",
            "role": "admin",
        },
    )
    assert forbidden.status_code == 403

    owner = client.post(
        f"{BASE}/admin/users",
        headers=admin_headers,
        json={
            "email": "owner-attempt@example.com",
            "password": "StrongPass123!",
            "full_name": "Owner Attempt",
            "role": "owner",
        },
    )
    assert owner.status_code == 400

    created_user = client.post(
        f"{BASE}/admin/users",
        headers=admin_headers,
        json={
            "email": "created.user@example.com",
            "password": "CreatedPass123!",
            "full_name": "Created User",
            "organisation": "Example Org",
            "role": "user",
        },
    )
    assert created_user.status_code == 201, created_user.text
    body = created_user.json()
    assert body["role"] == "user"
    assert body["email"] == "created.user@example.com"
    assert "password_hash" not in body
    assert client.get(f"{BASE}/admin/dashboard", headers=_login(client, "created.user@example.com", "CreatedPass123!")).status_code == 403

    created_admin = client.post(
        f"{BASE}/admin/users",
        headers=admin_headers,
        json={
            "email": "created.admin@example.com",
            "password": "CreatedAdmin123!",
            "full_name": "Created Admin",
            "role": "admin",
        },
    )
    assert created_admin.status_code == 201, created_admin.text
    assert created_admin.json()["role"] == "admin"
    admin_here = _login(client, "created.admin@example.com", "CreatedAdmin123!")
    assert client.get(f"{BASE}/admin/dashboard", headers=admin_here).status_code == 200

    duplicate = client.post(
        f"{BASE}/admin/users",
        headers=admin_headers,
        json={
            "email": "created.user@example.com",
            "password": "AnotherPass123!",
            "full_name": "Duplicate User",
        },
    )
    assert duplicate.status_code == 409


def test_company_verification_and_monitoring_crud(client: TestClient) -> None:
    headers, _ = _auth_client(client)
    company = client.post(
        f"{BASE}/company/verify",
        headers=headers,
        json={
            "company_name": "Example Technologies",
            "website_url": "https://example.com",
            "consent_external_lookups": False,
        },
    )
    assert company.status_code == 200, company.text
    assert isinstance(company.json(), dict)

    created = client.post(
        f"{BASE}/monitoring",
        headers=headers,
        json={
            "name": "Fraud watch",
            "company_names": ["Example Technologies"],
            "job_titles": ["Data Entry Operator"],
            "source_urls": [],
            "keywords": ["upfront fee"],
            "enabled": True,
            "notify_email": True,
            "notify_in_app": True,
        },
    )
    assert created.status_code == 201, created.text
    monitor_id = created.json()["id"]
    assert any(item["id"] == monitor_id for item in client.get(f"{BASE}/monitoring", headers=headers).json())
    assert client.delete(f"{BASE}/monitoring/{monitor_id}", headers=headers).status_code == 200


def test_notifications_endpoint_returns_paginated_results(client: TestClient) -> None:
    headers, _ = _auth_client(client)
    analysis = client.post(
        f"{BASE}/analysis/message",
        headers=headers,
        json={
            "text": "Pay a registration fee and share your OTP immediately to get this job.",
            "channel": "email",
            "sender": "fraud@example.net",
            "consent_external_lookups": False,
        },
    )
    assert analysis.status_code == 200
    notifications = client.get(f"{BASE}/notifications", headers=headers)
    assert notifications.status_code == 200
    payload = notifications.json()
    assert {"items", "total", "page", "page_size", "pages"} <= payload.keys()
    # Notifications are only created when the explainable score reaches 60; a
    # text-only submission is usually inconclusive, so both outcomes are valid.
    expected = 1 if analysis.json()["risk"]["score"] >= 60 else 0
    assert payload["total"] >= expected


def test_security_config_reports_turnstile_not_configured(client: TestClient) -> None:
    response = client.get(f"{BASE}/auth/security-config")
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["status"] == "not_configured"
    assert body["site_key"] is None
    assert client.get(f"{BASE}/system/config").json()["integrations"]["cloudflare_turnstile"] is False


def test_login_remembers_previous_signin_and_recognises_device(client: TestClient) -> None:
    credentials = _register(client)
    first = client.post(
        f"{BASE}/auth/login",
        json={**credentials, "device_id": "device-alpha", "remember_device": True},
    )
    assert first.status_code == 200, first.text
    assert first.json()["previous_signin"] is None
    assert first.json()["new_device"] is False
    assert first.json()["verification"] == "not_configured"

    second = client.post(
        f"{BASE}/auth/login",
        json={**credentials, "device_id": "device-alpha", "remember_device": True},
    )
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["new_device"] is False
    assert body["previous_signin"]["device"]
    assert body["previous_signin"]["at"]

    headers = {"Authorization": f"Bearer {body['access_token']}"}
    activity = client.get(f"{BASE}/auth/signin-activity", headers=headers)
    assert activity.status_code == 200
    assert len(activity.json()) == 2
    assert activity.json()[0]["known_device"] is True
    assert activity.json()[1]["known_device"] is False  # first sign-in has no prior device record


def test_new_device_signin_is_flagged_and_notifies_owner(client: TestClient) -> None:
    credentials = _register(client)
    client.post(f"{BASE}/auth/login", json={**credentials, "device_id": "device-alpha"})
    response = client.post(f"{BASE}/auth/login", json={**credentials, "device_id": "device-beta"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["new_device"] is True
    assert body["previous_signin"]["device"]

    headers = {"Authorization": f"Bearer {body['access_token']}"}
    activity = client.get(f"{BASE}/auth/signin-activity", headers=headers).json()
    assert activity[0]["known_device"] is False
    notifications = client.get(f"{BASE}/notifications", headers=headers).json()
    assert any(item["kind"] == "new_device_signin" for item in notifications["items"])


def test_turnstile_is_enforced_and_fails_closed(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.deps import get_app_settings
    from app.core.config import get_settings
    from app.services import turnstile_service

    settings = get_settings().model_copy(
        update={
            "turnstile_site_key": "public-site-key",
            "turnstile_secret_key": "private-secret-key",
            "turnstile_expected_hostname": "app.hireshield.io",
        }
    )
    monkeypatch.setitem(app.dependency_overrides, get_app_settings, lambda: settings)

    outcomes = {"accept": False}

    class FakeResponse:
        content = b"{}"

        def json(self) -> dict:
            return {
                "success": outcomes["accept"],
                "hostname": "app.hireshield.io",
                "error-codes": [] if outcomes["accept"] else ["invalid-input-response"],
            }

    monkeypatch.setattr(turnstile_service.requests, "post", lambda *args, **kwargs: FakeResponse())
    credentials = _register(client)

    missing = client.post(f"{BASE}/auth/login", json=credentials)
    assert missing.status_code == 400
    assert "verification" in missing.json()["detail"].lower()

    rejected = client.post(f"{BASE}/auth/login", json={**credentials, "turnstile_token": "bad-token"})
    assert rejected.status_code == 400

    outcomes["accept"] = True
    accepted = client.post(f"{BASE}/auth/login", json={**credentials, "turnstile_token": "good-token"})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["verification"] == "verified"
    assert client.get(f"{BASE}/auth/security-config").json()["enabled"] is True


def test_turnstile_provider_outage_denies_login(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.deps import get_app_settings
    from app.core.config import get_settings
    from app.services import turnstile_service

    settings = get_settings().model_copy(
        update={"turnstile_site_key": "site", "turnstile_secret_key": "secret"}
    )
    monkeypatch.setitem(app.dependency_overrides, get_app_settings, lambda: settings)

    def fail(*args: object, **kwargs: object) -> None:
        raise ConnectionError("provider unreachable")

    monkeypatch.setattr(turnstile_service.requests, "post", fail)
    credentials = _register(client)
    response = client.post(f"{BASE}/auth/login", json={**credentials, "turnstile_token": "any-token"})
    assert response.status_code == 400
    assert "temporarily unavailable" in response.json()["detail"]


def test_generic_offer_analysis_end_to_end(client: TestClient) -> None:
    """Offer submissions use honest offer rules and retain campaign uncertainty."""
    headers, _ = _auth_client(client)
    payload = {
        "text": (
            "Congratulations! You won a guaranteed prize. Share with 10 friends and pay a "
            "processing fee to claim your reward. Act now, today only."
        ),
        "offer_category": "giveaway",
        "company_name": "Example Brands",
        "consent_external_lookups": False,
        "client_request_id": f"offer-{uuid.uuid4().hex}",
    }
    response = client.post(f"{BASE}/analysis/offer", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["analysis_type"] == "offer"
    assert body["offer_category"] == "giveaway"
    assert body["status"] == "completed"
    assert any(pred["model_name"] == "offer_rule_fallback" for pred in body["model_predictions"])
    assert all("recruitment-text" not in pred["model_name"] for pred in body["model_predictions"])
    assert any(item["source"] == "offer_rules" for item in body["indicators"])
    assert "offer_rules" in body["sources_attempted"]
    assert any("authorised" in item.lower() for item in body["missing_evidence"])
    assert isinstance(body["risk"]["score"], int)

    report = client.get(f"{BASE}/reports/{body['id']}", headers=headers)
    assert report.status_code == 200


def test_analysis_exposes_brand_threat_and_image_engines(client: TestClient) -> None:
    """The three Stage 4 engines are visible in a completed report."""
    from app.core.config import Settings

    settings = Settings()
    admin_login = client.post(
        f"{BASE}/auth/login",
        json={"email": settings.admin_email, "password": settings.admin_password},
    )
    assert admin_login.status_code == 200, admin_login.text
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    domain = f"threat-{uuid.uuid4().hex[:8]}.example.com"
    imported = client.post(
        f"{BASE}/threat-intelligence/import",
        headers=admin_headers,
        json={"indicators": [{"kind": "domain", "value": domain, "severity": 0.8}]},
    )
    assert imported.status_code == 200, imported.text

    headers, _ = _auth_client(client)
    response = client.post(
        f"{BASE}/analysis/offer",
        headers=headers,
        json={
            "text": (
                "Limited giveaway announced today. Visit the official page and pay a small "
                "processing fee to claim your reward."
            ),
            "offer_category": "giveaway",
            "company_name": "Example Brands",
            "source_url": f"https://{domain}/claim",
            "consent_external_lookups": False,
            "client_request_id": f"offer-engines-{uuid.uuid4().hex}",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["image_intelligence"] == {}
    assert body["brand_intelligence"]["state"] in {
        "verified_company",
        "verified_official_campaign",
        "unverified_advertisement",
        "suspected_impersonation",
    }
    assert body["threat_intelligence"]["status"] == "ok"
    assert body["threat_intelligence"]["matches"]
    assert any(item["name"] == "threat_feed_match" for item in body["indicators"])
    assert "brand_verification" in body["sources_attempted"]
    assert "threat_indicator_store" in body["sources_attempted"]


def test_offer_submission_rejects_short_text_and_unknown_category(client: TestClient) -> None:
    headers, _ = _auth_client(client)
    assert client.post(
        f"{BASE}/analysis/offer",
        json={"text": "too short", "offer_category": "other"},
        headers=headers,
    ).status_code == 422
    long_text = "A perfectly normal community announcement with enough detail to be analysed."
    assert client.post(
        f"{BASE}/analysis/offer",
        json={"text": long_text, "offer_category": "lottery"},
        headers=headers,
    ).status_code == 422

