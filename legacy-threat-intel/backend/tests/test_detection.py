from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tests.conftest import make_event

from app.detection.rules import RuleEngine
from app.risk.scoring import RiskScorer, severity_for


def _settings(client):
    return client.app.state.settings


def test_single_failure_does_not_trigger_rule(client):
    events = [make_event("auth_failure", minutes_ago=1)]
    candidates = RuleEngine(_settings(client)).evaluate(events, {})
    assert all(candidate["rule_id"] != "R001" for candidate in candidates)


def test_repeated_failures_trigger_rule_and_evidence(client):
    # Anchor timestamps inside one 15-minute bucket; "now" can straddle a boundary.
    anchor = datetime(2026, 1, 1, 12, 5, tzinfo=timezone.utc)
    events = [make_event("auth_failure", timestamp=anchor + timedelta(minutes=index)) for index in range(6)]
    candidates = RuleEngine(_settings(client)).evaluate(events, {})
    repeated = [candidate for candidate in candidates if candidate["rule_id"] == "R001"]
    assert len(repeated) == 1
    assert repeated[0]["signals"]["failed_login_count"] == 6
    assert len(repeated[0]["event_ids"]) == 6
    assert repeated[0]["reasons"]


def test_success_after_failures(client):
    anchor = datetime(2026, 1, 1, 12, 5, tzinfo=timezone.utc)
    events = [make_event("auth_failure", timestamp=anchor + timedelta(minutes=index)) for index in range(5)]
    events.append(make_event("auth_success", timestamp=anchor + timedelta(minutes=5)))
    candidates = RuleEngine(_settings(client)).evaluate(events, {})
    assert any(candidate["rule_id"] == "R003" for candidate in candidates)


def test_risk_score_is_bounded_and_explained(client):
    candidate = {
        "type": "rule",
        "base_score": 70,
        "confidence": 0.8,
        "ti_confidence": 0.9,
        "asset_criticality": 4,
        "correlation_evidence": 0.5,
        "reasons": ["test evidence"],
        "event_ids": ["evt_1"],
    }
    result = RiskScorer(_settings(client)).score(candidate)
    assert 0 <= result["risk_score"] <= 100
    assert len(result["contributing_signals"]) == 5
    assert result["calibrated_probability"] is False
    assert result["event_references"] == ["evt_1"]
    assert severity_for(90) == "critical"
    assert severity_for(5) == "informational"
