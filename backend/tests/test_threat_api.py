"""Admin API coverage for the optional threat-indicator registry."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

os.environ.setdefault("MONGODB_URI", "mongomock://")
os.environ.setdefault("CELERY_ENABLED", "false")
os.environ.setdefault("TASK_ALWAYS_EAGER", "true")
os.environ.setdefault("SEED_DEMO_DATA", "true")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings  # noqa: E402
from app.main import app  # noqa: E402

BASE = "/api/v1/threat-intelligence"


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_threat_registry_requires_admin(client: TestClient):
    email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "StrongPass123!",
            "full_name": "Registry Tester",
            "consent_privacy": True,
            "consent_terms": True,
        },
    )
    assert registered.status_code == 201
    headers = _headers(client, email, "StrongPass123!")
    assert client.get(f"{BASE}/sources", headers=headers).status_code == 403


def test_admin_can_register_import_and_list_indicators(client: TestClient):
    settings = Settings()
    headers = _headers(client, settings.admin_email, settings.admin_password)

    sources = client.get(f"{BASE}/sources", headers=headers)
    assert sources.status_code == 200, sources.text
    assert any(item["source_id"] == "operator_import" for item in sources.json()["sources"])

    rejected = client.post(
        f"{BASE}/sources",
        headers=headers,
        json={"source_id": "private-feed", "name": "Private Feed", "url": "http://127.0.0.1/feed.json"},
    )
    assert rejected.status_code == 400

    imported = client.post(
        f"{BASE}/import",
        headers=headers,
        json={"indicators": [{"kind": "domain", "value": "blocked-offer.example.com", "severity": 0.7}]},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["ingested"] == 1

    rows = client.get(f"{BASE}/indicators", headers=headers)
    assert rows.status_code == 200
    assert any(item["normalized_value"] == "blocked-offer.example.com" for item in rows.json()["items"])
