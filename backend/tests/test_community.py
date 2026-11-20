"""Stage 6 community-report and moderation integration tests."""

from __future__ import annotations

import os
import uuid

os.environ["MONGODB_URI"] = "mongomock://"
os.environ["CELERY_ENABLED"] = "false"
os.environ["TASK_ALWAYS_EAGER"] = "true"
os.environ["SEED_DEMO_DATA"] = "true"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

BASE = "/api/v1"
ADMIN_EMAIL = "admin@hireshield.io"
ADMIN_PASSWORD = "AdminPass123!"


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _register(client: TestClient, email: str | None = None) -> dict:
    payload = {
        "email": email or f"community-{uuid.uuid4().hex[:10]}@example.com",
        "password": "StrongPass123!",
        "full_name": "Community Tester",
        "consent_privacy": True,
        "consent_terms": True,
    }
    response = client.post(f"{BASE}/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return payload


def _login(client: TestClient, email: str, password: str = "StrongPass123!") -> dict[str, str]:
    response = client.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _user(client: TestClient) -> dict[str, str]:
    credentials = _register(client)
    return _login(client, credentials["email"])


def _analysis(client: TestClient, headers: dict[str, str], company: str = "Stage Six Recruitment Ltd") -> dict:
    response = client.post(
        f"{BASE}/analysis/job",
        headers=headers,
        json={
            "text": "We are reviewing applications for a remoteOperations role. Further details are available on request.",
            "company_name": company,
            "job_title": "Operations Assistant",
            "consent_external_lookups": False,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _community(client: TestClient, headers: dict[str, str], analysis_id: str, details: str) -> dict:
    response = client.post(
        f"{BASE}/reports/community",
        headers=headers,
        json={
            "analysis_id": analysis_id,
            "claim_type": "missed_fraud",
            "details": details,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _review(client: TestClient, report_id: str, state: str, **extra: str) -> dict:
    admin = _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    response = client.patch(
        f"{BASE}/admin/reports/{report_id}",
        headers=admin,
        json={"moderation_state": state, **extra},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _admin_headers(client: TestClient) -> dict[str, str]:
    return _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)


def _report_indicators(result: dict) -> list[dict]:
    """Only indicators created by Stage 6 community reports, not anomaly history."""

    return [item for item in result["indicators"] if item.get("name") == "community_independently_corroborated"]


def test_corrections_and_community_reports_are_distinct_with_duplicate_detection(client: TestClient) -> None:
    headers = _user(client)
    analysis = _analysis(client, headers)
    analysis_id = analysis["id"]

    correction = client.post(
        f"{BASE}/reports/feedback",
        headers=headers,
        json={
            "analysis_id": analysis_id,
            "report_type": "false_positive",
            "details": "The salary range in this assessment was entered incorrectly.",
        },
    )
    assert correction.status_code == 200, correction.text
    correction_data = correction.json()
    assert correction_data["category"] == "correction"
    assert correction_data["moderation_state"] == "pending"
    assert correction_data["entity_key"]
    assert correction_data["status"] == "pending_review"

    duplicate_correction = client.post(
        f"{BASE}/reports/feedback",
        headers=headers,
        json={
            "analysis_id": analysis_id,
            "report_type": "false_positive",
            "details": "The salary range in this assessment was entered incorrectly!",
        },
    )
    assert duplicate_correction.status_code == 200, duplicate_correction.text
    assert duplicate_correction.json()["id"] == correction_data["id"]
    assert duplicate_correction.json()["duplicate"] is True

    community = _community(client, headers, analysis_id, "This employer demanded an advance fee.")
    assert community["category"] == "community"
    assert community["report_type"] == "missed_fraud"
    assert community["id"] != correction_data["id"]
    assert community["entity_key"] == correction_data["entity_key"]

    duplicate_community = _community(client, headers, analysis_id, "This employer demanded an ADVANCE fee.")
    assert duplicate_community["id"] == community["id"]
    assert duplicate_community["duplicate"] is True
    assert duplicate_community["duplicate_count"] >= 1

    other_claim = _community(client, headers, analysis_id, "A different recruiter used the same brand logo.")
    assert other_claim["id"] != community["id"]
    assert other_claim["duplicate_group_key"] != community["duplicate_group_key"]


def test_report_paths_enforce_analysis_ownership(client: TestClient) -> None:
    owner = _user(client)
    stranger = _user(client)
    analysis = _analysis(client, owner)

    correction = client.post(
        f"{BASE}/reports/feedback",
        headers=stranger,
        json={
            "analysis_id": analysis["id"],
            "report_type": "false_positive",
            "details": "I want to change somebody else's assessment.",
        },
    )
    assert correction.status_code == 403

    community = client.post(
        f"{BASE}/reports/community",
        headers=stranger,
        json={
            "analysis_id": analysis["id"],
            "claim_type": "missed_fraud",
            "details": "I want to report an entity I cannot access.",
        },
    )
    assert community.status_code == 403

    assert client.get(f"{BASE}/reports/{analysis['id']}", headers=stranger).status_code == 403
    assert _community(client, owner, analysis["id"], "The owner may report their own analysis.")["category"] == "community"


def test_one_verified_report_never_creates_community_risk_signal(client: TestClient) -> None:
    # Fresh users for each observation keep the historical/anomaly engine from
    # reacting to submission repetition rather than to community reports.
    first = _user(client)
    second = _user(client)
    analysis = _analysis(client, first)
    analysis_id = analysis["id"]

    baseline = _analysis(client, _user(client))
    assert baseline["community_intelligence"]["status"] == "insufficient_independent_reports"
    assert not _report_indicators(baseline)

    report = _community(client, first, analysis_id, "The same company requested an advance payment.")
    _review(client, report["id"], "verified", review_notes="Moderator confirmed the report was reviewed.")

    after_one = _analysis(client, _user(client))
    assert after_one["community_intelligence"]["status"] == "insufficient_independent_reports"
    assert after_one["community_intelligence"]["independent_reporters"] == 1
    assert not _report_indicators(after_one)
    # Historical/anomaly signals may shift slightly from repeat analysis
    # submissions, but the single community report itself creates no indicator
    # and must not move the risk classification band.
    assert after_one["risk"]["category"] == baseline["risk"]["category"]

    # A different reporter on the same analysis is independent corroboration.
    second_analysis = _analysis(client, second)
    second_report = _community(client, second, second_analysis["id"], "The same company requested an advance payment.")
    _review(client, second_report["id"], "verified", review_notes="Second independent report reviewed.")

    after_two = _analysis(client, _user(client))
    assert after_two["community_intelligence"]["status"] == "corroborated"
    assert after_two["community_intelligence"]["independent_reporters"] == 2
    assert after_two["community_intelligence"]["weighted_support"] >= 0.5
    community_indicators = _report_indicators(after_two)
    assert len(community_indicators) == 1
    assert community_indicators[0]["name"] == "community_independently_corroborated"
    assert community_indicators[0]["independently_verified"] is False
    assert "not proof of fraud" in community_indicators[0]["description"].lower()


def test_moderation_states_false_reports_reputation_audit_and_rbac(client: TestClient) -> None:
    reporter = _user(client)
    analysis = _analysis(client, reporter)
    report = _community(client, reporter, analysis["id"], "This advert was published without authorisation.")

    non_admin = _user(client)
    denied = client.patch(
        f"{BASE}/admin/reports/{report['id']}",
        headers=non_admin,
        json={"moderation_state": "verified"},
    )
    assert denied.status_code == 403

    legacy = _review(client, report["id"], "verified", status="reviewed")
    assert legacy["moderation_state"] == "verified"

    missing_reason = client.patch(
        f"{BASE}/admin/reports/{report['id']}",
        headers=_admin_headers(client),
        json={"moderation_state": "false_report"},
    )
    assert missing_reason.status_code == 400

    false_report = client.patch(
        f"{BASE}/admin/reports/{report['id']}",
        headers=_admin_headers(client),
        json={
            "moderation_state": "false_report",
            "review_notes": "Reporter acknowledged a mistaken submission.",
            "false_report_reason": "Evidence submitted with the report was misread.",
        },
    )
    assert false_report.status_code == 200, false_report.text
    assert false_report.json()["status"] == "dismissed"
    assert false_report.json()["is_false_report"] is True
    assert false_report.json()["false_report_reason"]

    invalid = client.patch(
        f"{BASE}/admin/reports/{report['id']}",
        headers=_admin_headers(client),
        json={"moderation_state": "corroborated"},
    )
    assert invalid.status_code == 409

    audits = client.get(f"{BASE}/admin/audit-logs?action=report&page_size=100", headers=_admin_headers(client))
    assert audits.status_code == 200
    actions = [item["action"] for item in audits.json()["items"]]
    assert "admin.report_verified" in actions
    assert "admin.report_marked_false" in actions
    false_audit = next(item for item in audits.json()["items"] if item["action"] == "admin.report_marked_false")
    assert false_audit["metadata"]["previous_state"] == "verified"
    assert false_audit["metadata"]["moderation_state"] == "false_report"

    next_report = _community(client, reporter, analysis["id"], "A separate allegation about the same listing.")
    assert next_report["reporter_reputation"]["score"] < 0.5
    assert next_report["reporter_reputation"]["basis"]["false_report"] >= 1

    after_false = _analysis(client, reporter)
    assert after_false["community_intelligence"]["status"] == "insufficient_independent_reports"
    assert not _report_indicators(after_false)
