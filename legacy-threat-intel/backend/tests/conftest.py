"""Test fixtures: in-memory MongoDB, no scheduler, no external calls."""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import mongomock
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.utils import make_id, utcnow  # noqa: E402


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        mongodb_uri="mongodb://localhost:27017",
        mongodb_db="tip_test",
        api_key="test-key",
        auth_enabled=False,
        scheduler_enabled=False,
        change_stream_enabled=False,
        ti_enabled=False,
        model_dir=str(tmp_path / "models"),
        enabled_sources=["application_log"],
        authorized_sources=["application_log"],
    )


@pytest.fixture
def client(settings: Settings):
    app = create_app(settings, mongo_client=mongomock.MongoClient())
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def repos(client: TestClient):
    return client.app.state.repos


def make_event(
    event_type: str = "auth_failure",
    *,
    source_ip: str = "198.51.100.77",
    actor_user: str = "alice",
    minutes_ago: int = 0,
    **extra,
) -> dict:
    event = {
        "event_id": make_id("evt", event_type, source_ip, actor_user, minutes_ago, extra),
        "event_type": event_type,
        "source_ip": source_ip,
        "actor_user": actor_user,
        "timestamp": utcnow() - timedelta(minutes=minutes_ago),
        "asset_criticality": 0,
        "indicators": [],
        "message": "test event",
        "dedupe_key": make_id("dedupe", event_type, source_ip, actor_user, minutes_ago, extra),
    }
    event.update(extra)
    return event
