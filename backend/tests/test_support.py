"""Support chat endpoint, persistence and grounded FAQ matching tests."""

from __future__ import annotations

import os
from uuid import uuid4

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


def session() -> str:
    return uuid4().hex


def ask(client: TestClient, message: str, session_id: str | None = None):
    return client.post(
        f"{BASE}/chat",
        json={"message": message, "session_id": session_id or session()},
    )


def test_grounded_answer_returns_sources(client: TestClient) -> None:
    response = ask(client, "How is the risk score calculated?")
    assert response.status_code == 200
    body = response.json()
    assert body["grounded"] is True
    assert "weighted" in body["answer"].lower()
    assert body["matched_question"]
    assert body["sources"]
    assert body["session_id"]
    assert body["created_at"]


def test_billing_answer_states_no_sensitive_data_collection(client: TestClient) -> None:
    response = ask(client, "Can I pay by card or PAN?")
    assert response.status_code == 200
    body = response.json()
    assert body["grounded"] is True
    assert "never collects card" in body["answer"]


def test_unknown_question_gets_honest_fallback(client: TestClient) -> None:
    response = ask(client, "What is the weather in Delhi?")
    assert response.status_code == 200
    body = response.json()
    assert body["grounded"] is False
    assert "won’t guess" in body["answer"]
    assert len(body["suggestions"]) >= 3


def test_chat_logs_input_and_output_then_clears(client: TestClient) -> None:
    session_id = session()
    response = ask(client, "How is the risk score calculated?", session_id)
    assert response.status_code == 200

    history = client.get(f"{BASE}/chat", params={"session_id": session_id})
    assert history.status_code == 200
    messages = history.json()
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[0]["text"] == "How is the risk score calculated?"
    assert messages[1]["text"] == response.json()["answer"]
    assert messages[1]["grounded"] is True
    assert all(message["session_id"] == session_id for message in messages)
    assert all(message["id"] for message in messages)

    cleared = client.delete(f"{BASE}/chat", params={"session_id": session_id})
    assert cleared.status_code == 200
    assert cleared.json()["deleted"] == 2
    assert client.get(f"{BASE}/chat", params={"session_id": session_id}).json() == []


def test_short_message_is_rejected(client: TestClient) -> None:
    response = client.post(
        f"{BASE}/chat",
        json={"message": "x", "session_id": session()},
    )
    assert response.status_code == 422


def test_invalid_session_id_is_rejected(client: TestClient) -> None:
    assert client.post(
        f"{BASE}/chat",
        json={"message": "How does it work?", "session_id": "bad"},
    ).status_code == 422
    assert client.get(f"{BASE}/chat", params={"session_id": "bad"}).status_code == 422


def test_matcher_does_not_invent_answers() -> None:
    assert match_faq("Tell me something completely unrelated") is None
    assert match_faq("why is the first request slow on render") is not None
