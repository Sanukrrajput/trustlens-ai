"""Support chat endpoint and grounded FAQ matching tests."""

from __future__ import annotations

import os

os.environ["MONGODB_URI"] = "mongomock://"
os.environ["CELERY_ENABLED"] = "false"
os.environ["TASK_ALWAYS_EAGER"] = "true"
os.environ["SEED_DEMO_DATA"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.support.faq import match_faq  # noqa: E402

BASE = "/api/v1/support"


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def test_grounded_answer_returns_sources(client: TestClient) -> None:
    response = client.post(f"{BASE}/chat", json={"message": "How is the risk score calculated?"})
    assert response.status_code == 200
    body = response.json()
    assert body["grounded"] is True
    assert "weighted" in body["answer"].lower()
    assert body["matched_question"]
    assert body["sources"]


def test_billing_answer_states_no_sensitive_data_collection(client: TestClient) -> None:
    response = client.post(f"{BASE}/chat", json={"message": "Can I pay by card or PAN?"})
    assert response.status_code == 200
    body = response.json()
    assert body["grounded"] is True
    assert "never collects card" in body["answer"]


def test_unknown_question_gets_honest_fallback(client: TestClient) -> None:
    response = client.post(f"{BASE}/chat", json={"message": "What is the weather in Delhi?"})
    assert response.status_code == 200
    body = response.json()
    assert body["grounded"] is False
    assert "won’t guess" in body["answer"]
    assert len(body["suggestions"]) >= 3


def test_short_message_is_rejected(client: TestClient) -> None:
    assert client.post(f"{BASE}/chat", json={"message": "x"}).status_code == 422


def test_matcher_does_not_invent_answers() -> None:
    assert match_faq("Tell me something completely unrelated") is None
    assert match_faq("why is the first request slow on render") is not None
