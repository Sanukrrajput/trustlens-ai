"""Stage 8 hardening tests: request IDs, rate limits, retention and backups."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import uuid
from datetime import timedelta
from pathlib import Path
from types import ModuleType

os.environ.setdefault("MONGODB_URI", "mongomock://")
os.environ.setdefault("CELERY_ENABLED", "false")
os.environ.setdefault("TASK_ALWAYS_EAGER", "true")
os.environ.setdefault("SEED_DEMO_DATA", "false")

import pytest  # noqa: E402
from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.deps import enforce_rate_limit, get_app_settings  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.core.security import utcnow  # noqa: E402
from app.db.mongo import MongoDBService  # noqa: E402
from app.db.repositories import Repositories  # noqa: E402
from app.main import app  # noqa: E402
from app.services.retention_service import enforce_retention  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def _load_script(name: str) -> ModuleType:
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def repos() -> Repositories:
    settings = Settings(mongodb_uri="mongomock://", seed_demo_data=False)
    mongo = MongoDBService(settings)
    mongo.setup()
    yield Repositories(mongo)
    mongo.close()


def test_rate_limit_uses_configuration_and_returns_retry_after() -> None:
    limited_app = FastAPI()

    @limited_app.get("/limited", dependencies=[Depends(enforce_rate_limit)])
    def limited() -> dict[str, bool]:
        return {"ok": True}

    policy = Settings(rate_limit_per_minute=2, rate_limit_window_seconds=45)
    limited_app.dependency_overrides[get_app_settings] = lambda: policy

    with TestClient(limited_app) as limited_client:
        assert limited_client.get("/limited").status_code == 200
        assert limited_client.get("/limited").status_code == 200
        rejected = limited_client.get("/limited")
        assert rejected.status_code == 429
        assert rejected.headers["retry-after"] == "45"
        assert rejected.json()["detail"] == "rate limit exceeded"


def test_invalid_operational_settings_are_rejected() -> None:
    with pytest.raises(ValueError, match="RATE_LIMIT_PER_MINUTE"):
        Settings(rate_limit_per_minute=0)
    with pytest.raises(ValueError, match="RETENTION_DAYS"):
        Settings(retention_days=0)
    with pytest.raises(ValueError, match="RATE_LIMIT_WINDOW_SECONDS"):
        Settings(rate_limit_window_seconds=0)


def test_request_id_is_echoed_and_logged(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    supplied = "Req" + uuid.uuid4().hex[:12]
    with caplog.at_level("INFO"):
        response = client.get("/health", headers={"X-Request-ID": supplied})
    assert response.status_code == 200
    assert response.headers["x-request-id"] == supplied
    assert any(getattr(record, "ctx_request_id", None) == supplied for record in caplog.records)

    generated = client.get("/health", headers={"X-Request-ID": "<script>alert(1)</script>"})
    assert generated.headers["x-request-id"] != "<script>alert(1)</script>"
    assert len(generated.headers["x-request-id"]) == 32


def test_retention_purge_respects_configuration(repos: Repositories) -> None:
    settings = Settings(
        mongodb_uri="mongomock://",
        seed_demo_data=False,
        retention_days=10,
        audit_retention_days=5,
    )
    old = utcnow() - timedelta(days=30)
    recent = utcnow()
    for collection, field in (("fraud_analyses", "created_at"), ("audit_logs", "created_at")):
        repos.mongo.db[collection].insert_many(
            [{field: old, "marker": "expired"}, {field: recent, "marker": "keep"}]
        )

    summary = enforce_retention(repos, settings, audit=False)
    assert summary["status"] == "ok"
    assert summary["deleted"]["fraud_analyses"] == 1
    assert summary["deleted"]["audit_logs"] == 1
    assert repos.mongo.db["fraud_analyses"].count_documents({"marker": "keep"}) == 1
    assert repos.mongo.db["audit_logs"].count_documents({"marker": "keep"}) == 1

    disabled = enforce_retention(
        repos, settings.model_copy(update={"retention_enabled": False}), audit=False
    )
    assert disabled["status"] == "disabled"
    assert disabled["total_deleted"] == 0


def test_backup_verify_and_restore_round_trip(tmp_path: Path) -> None:
    mongomock = pytest.importorskip("mongomock")
    backup = _load_script("backup_tool")
    client = mongomock.MongoClient()
    client["source"]["offers"].insert_many(
        [{"_id": "a", "text": "first offer"}, {"_id": "b", "text": "second offer"}]
    )

    created = backup.create_backup(client, "source", tmp_path)
    assert created["status"] == "ok"
    assert created["documents"] == 2
    verified = backup.verify_backup(created["path"])
    assert verified["status"] == "ok"
    assert verified["collections"] == 1

    refused = backup.restore_backup(client, "target", created["path"])
    assert refused["status"] == "refused"

    restored = backup.restore_backup(client, "target", created["path"], confirm=True)
    assert restored["status"] == "ok"
    assert restored["total_restored"] == 2
    assert client["target"]["offers"].count_documents({}) == 2

    manifest_path = Path(created["path"]) / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["collections"]["offers"]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(backup.BackupError, match="checksum"):
        backup.verify_backup(created["path"])


def test_secret_scan_detects_planted_credentials_and_allows_templates() -> None:
    scanner = _load_script("secret_scan")
    credential = "rzp_" + "live_abcdefghijklmnop"
    assignment = "api_" + "key = '" + credential + "'\n"
    findings = scanner.scan_text("candidate.py", assignment)
    assert any(item["kind"] == "razorpay_live_key" for item in findings)
    assert scanner.scan_text(".env.example", "SECRET_KEY=development-only-secret-change-before-launch\n") == []
    result = scanner.scan([])
    assert result["status"] == "ok"
    assert result["tracked_env_files"] == []
    assert result["tracked_backups"] == []
