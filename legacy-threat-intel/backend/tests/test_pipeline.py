from __future__ import annotations

from datetime import timedelta

from app.utils import make_id, utcnow
from tests.conftest import make_event


def test_dedupe_and_detection_pipeline(client):
    repos = client.app.state.repos
    event = make_event("auth_failure", source_ip="198.51.100.77", actor_user="alice")
    document = dict(event)
    document.update(
        ingested_at=utcnow(),
        expires_at=utcnow() + timedelta(days=1),
        needs_enrichment=False,
        dedupe_key=event["dedupe_key"],
    )
    stats = repos.events.bulk_upsert([document, document])
    assert stats["inserted"] == 1
    assert stats["duplicates"] == 1
    assert repos.events.count() == 1

    services = client.app.state.services
    detection_result = services["detection"].process()
    assert detection_result["events_processed"] == 1
    assert detection_result["ml_status"].startswith("untrained")
    assert repos.events.count({"processed_at": {"$exists": True}}) == 1

    correlation_result = services["correlator"].correlate()
    assert correlation_result["incidents_created"] >= 0
    first_count = repos.incidents.count()
    services["correlator"].correlate()
    assert repos.incidents.count() == first_count


def test_correlation_updates_existing_incident(client):
    repos = client.app.state.repos
    detection = {
        "detection_id": make_id("det", "test"),
        "detection_key": make_id("key", "test"),
        "title": "Test detection",
        "severity": "high",
        "risk_score": 72.5,
        "rule_id": "R001",
        "type": "rule",
        "source_ip": "198.51.100.77",
        "window_start": utcnow(),
        "created_at": utcnow(),
        "event_ids": ["evt_1"],
        "detection_reasons": ["test evidence"],
    }
    repos.detections.upsert(detection)
    services = client.app.state.services
    first = services["correlator"].correlate()
    assert first["incidents_created"] == 1
    incident = repos.incidents.find({})[0]
    assert incident["risk_score"] == 72.5
    detection["risk_score"] = 88.0
    detection["event_ids"] = ["evt_1", "evt_2"]
    repos.detections.upsert(detection)
    repos.detections.update_one({"detection_id": detection["detection_id"]}, {"$unset": {"incident_id": ""}})
    second = services["correlator"].correlate()
    assert second["incidents_updated"] == 1
    assert repos.incidents.count() == 1
    updated = repos.incidents.find({})[0]
    assert updated["risk_score"] == 88.0
    assert "evt_2" in updated["event_ids"]
