from __future__ import annotations

import re

import mongomock
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.utils import make_id, utcnow


def test_health_and_auth_disabled(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert client.get("/api/v1/admin/me").json()["authenticated"] is True


def test_status_endpoint_requires_api_key_when_auth_enabled(settings: Settings):
    settings.auth_enabled = True
    app = create_app(settings, mongo_client=mongomock.MongoClient())
    with TestClient(app) as auth_client:
        assert auth_client.get("/health").status_code == 200
        assert auth_client.get("/api/v1/status").status_code == 401
        assert auth_client.get("/api/v1/status", headers={"X-API-Key": "wrong"}).status_code == 401
        assert auth_client.get("/api/v1/status", headers={"X-API-Key": "test-key"}).status_code == 200


def test_overview_uses_database_values(client):
    repos = client.app.state.repos
    repos.events.insert_one(
        {
            "event_id": make_id("evt", "overview"),
            "dedupe_key": make_id("dedupe", "overview"),
            "timestamp": utcnow(),
            "source_type": "test",
            "event_type": "auth_failure",
        }
    )
    summary = client.get("/api/v1/core/overview/summary").json()
    assert summary["total_security_events"] == 1
    assert summary["active_incidents"] == 0
    assert isinstance(summary["data_source_health"], list)


def test_private_indicator_is_not_sent_externally(client):
    response = client.post(
        "/api/v1/intel/indicators/enrich",
        params={"force": True},
        json={"type": "ip", "value": "10.0.0.5"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["external_lookup"] is False
    assert body["indicator"]["routable"] is False


def test_invalid_indicator_rejected(client):
    response = client.post(
        "/api/v1/intel/indicators/enrich",
        json={"type": "domain", "value": "not a domain!"},
    )
    assert response.status_code == 400


def test_response_action_requires_authorization(client):
    repos = client.app.state.repos
    repos.incidents.insert_one(
        {
            "incident_id": "inc_test",
            "title": "test",
            "severity": "high",
            "risk_score": 70,
            "first_seen": utcnow(),
        }
    )
    created = client.post(
        "/api/v1/admin/response-actions",
        json={
            "incident_id": "inc_test",
            "action_type": "block_ip",
            "target": "198.51.100.77",
            "rationale": "test",
        },
    )
    assert created.status_code == 200
    assert created.json()["executed"] is False
    approval = client.post(
        f"/api/v1/admin/response-actions/{created.json()['action_id']}/approve",
        params={"approver": "analyst", "note": "test"},
    )
    assert approval.status_code == 403
    assert repos.actions.count() == 1


def test_governance_endpoints_used_by_dashboard(client):
    repos = client.app.state.repos

    sources = client.get("/api/v1/intel/sources")
    assert sources.status_code == 200
    assert any(item["name"] == "windows_eventlog" for item in sources.json()["items"])

    jobs = client.get("/api/v1/intel/jobs")
    assert jobs.status_code == 200
    assert jobs.json()["total"] == 0

    settings = client.get("/api/v1/intel/settings")
    assert settings.status_code == 200
    assert "environment" in settings.json()
    assert settings.json()["environment"]["api_key"] == "***configured***"

    updated = client.put(
        "/api/v1/intel/settings",
        json={"overrides": {"rule_failed_login_threshold": 7}},
    )
    assert updated.status_code == 200
    assert updated.json()["thresholds"]["rule_failed_login_threshold"] == 7

    repos.notifications.insert_one(
        {
            "notification_id": "ntf_smoke",
            "title": "Smoke test alert",
            "message": "verify notification center",
            "severity": "high",
            "read": False,
            "created_at": utcnow(),
        }
    )
    notifications = client.get("/api/v1/admin/notifications", params={"unread_only": True})
    assert notifications.status_code == 200
    assert notifications.json()["total"] == 1
    marked = client.post("/api/v1/admin/notifications/ntf_smoke/read")
    assert marked.status_code == 200
    assert repos.notifications.count({"read": True}) == 1

    repos.audit.write("smoke_action", "analyst", {"key": "value"})
    audit = client.get("/api/v1/admin/audit-logs", params={"q": "smoke", "actor": "analyst"})
    assert audit.status_code == 200
    assert audit.json()["total"] == 1

    health = client.get("/api/v1/intel/system/health")
    assert health.status_code == 200
    assert "counts" in health.json()
    assert client.get("/api/v1/status").status_code == 200


def test_asset_upsert_persists_and_is_audited(client):
    repos = client.app.state.repos
    payload = {
        "asset_id": "ast_regression",
        "hostname": "workstation-1",
        "ip_addresses": ["198.51.100.77"],
        "criticality": 3,
        "owner": "SOC",
    }
    created = client.post("/api/v1/intel/assets", json=payload)
    assert created.status_code == 200
    assert re.fullmatch(r"[0-9a-f]{24}", created.json()["_id"])
    assert repos.assets.count({"asset_id": "ast_regression"}) == 1
    assert repos.audit.count({"action": "asset_upserted"}) == 1

    payload["criticality"] = 5
    updated = client.post("/api/v1/intel/assets", json=payload)
    assert updated.status_code == 200
    assert repos.assets.count({"asset_id": "ast_regression"}) == 1
    assert repos.assets.find_one({"asset_id": "ast_regression"})["criticality"] == 5
