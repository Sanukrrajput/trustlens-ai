"""Host allow-list behaviour, including the infrastructure health exemption."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import HealthCheckTrustedHostMiddleware


def _client() -> TestClient:
    probe_app = FastAPI()
    probe_app.add_middleware(
        HealthCheckTrustedHostMiddleware, allowed_hosts=["allowed.test"]
    )

    @probe_app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @probe_app.get("/api/v1/health")
    def api_health() -> dict[str, str]:
        return {"status": "ok"}

    return TestClient(probe_app)


def test_health_endpoint_bypasses_host_allow_list() -> None:
    client = _client()
    response = client.get("/health", headers={"Host": "internal-probe"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_application_routes_still_enforce_host_allow_list() -> None:
    client = _client()
    denied = client.get("/api/v1/health", headers={"Host": "evil.example"})
    allowed = client.get("/api/v1/health", headers={"Host": "allowed.test"})
    assert denied.status_code == 400
    assert allowed.status_code == 200
