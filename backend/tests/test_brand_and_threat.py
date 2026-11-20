"""Tests for brand/campaign states and the threat-indicator store."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings  # noqa: E402
from app.db.mongo import MongoDBService  # noqa: E402
from app.db.repositories import Repositories  # noqa: E402
from app.intelligence.brand_verification import BrandVerifier  # noqa: E402
from app.intelligence.threat_indicators import (  # noqa: E402
    ThreatIndicatorStore,
    normalise_indicator_value,
)


@pytest.fixture()
def repos():
    settings = Settings(mongodb_uri="mongomock://", seed_demo_data=False)
    mongo = MongoDBService(settings)
    mongo.setup()
    yield Repositories(mongo)
    mongo.close()


def _verified_company() -> dict:
    return {"verification_status": "verified_with_evidence"}


def _unverified_company() -> dict:
    return {"verification_status": "unverified"}


def test_brand_verification_without_claim_is_not_attempted():
    result = BrandVerifier().verify()
    assert result["state"] == "not_attempted"
    assert result["status"] == "not_attempted"


def test_registry_match_does_not_verify_a_campaign():
    result = BrandVerifier().verify(
        claimed_brand="Example Technologies",
        campaign={"source_url": "https://advert.example.com/offer"},
        company_result=_verified_company(),
        consent_external_lookups=True,
    )
    assert result["state"] == "verified_company"
    assert result["entity_verified"] is True
    assert result["campaign_verified"] is False
    assert any("authorised this specific offer" in item for item in result["missing_evidence"])


def test_official_campaign_requires_independent_evidence():
    result = BrandVerifier().verify(
        claimed_brand="Example Technologies",
        campaign={"campaign_id": "summer-offer"},
        company_result=_verified_company(),
        campaign_evidence=[
            {
                "claim": "official campaign authorisation",
                "source": "official brand channel",
                "source_type": "official_brand_channel",
                "reference_url": "https://example.com/official/campaign/summer-offer",
                "independently_verified": True,
                "observed_at": "2026-01-01T00:00:00+00:00",
            }
        ],
        consent_external_lookups=True,
    )
    assert result["state"] == "verified_official_campaign"
    assert result["campaign_verified"] is True


def test_user_supplied_advert_cannot_verify_campaign():
    result = BrandVerifier().verify(
        claimed_brand="Example Technologies",
        campaign={"source_url": "https://advert.example.com/offer"},
        company_result=_verified_company(),
        campaign_evidence=[
            {
                "claim": "we are authorised",
                "source_type": "user_supplied_advertisement",
                "reference_url": "https://advert.example.com/offer",
                "independently_verified": True,
            }
        ],
    )
    assert result["state"] == "verified_company"
    assert result["campaign_verified"] is False


def test_lookalike_domain_yields_suspected_impersonation_heuristic():
    domain = {
        "indicators": [
            {"name": "domain_lookalike_heuristic", "status": "suspicious", "severity": 0.3}
        ]
    }
    result = BrandVerifier().verify(
        claimed_brand="State Bank of India",
        campaign={"source_url": "https://sbi-secure-login.in/offer"},
        company_result=_unverified_company(),
        domain_result=domain,
    )
    assert result["state"] == "suspected_impersonation"
    assert any("heuristic" in item.lower() for item in result["limitations"])
    assert not any(item["status"] == "confirmed_malicious" for item in result["indicators"])


def test_threat_match_for_brand_is_suspected_not_proof():
    result = BrandVerifier().verify(
        claimed_brand="Example Technologies",
        campaign={"source_url": "https://offer.example.net"},
        company_result=_unverified_company(),
        threat_matches=[
            {
                "kind": "brand_impersonation",
                "value": "Example Technologies",
                "description": "Stored indicator references this brand.",
                "source": "operator_import",
            }
        ],
    )
    assert result["state"] == "suspected_impersonation"
    indicator = next(item for item in result["indicators"] if item["name"] == "brand_impersonation_suspected")
    assert indicator["status"] == "suspicious"


def test_value_normalisation():
    assert normalise_indicator_value("domain", "HTTPS://WWW.Example.com/path") == "example.com"
    assert normalise_indicator_value("email", "  HR@Example.COM ") == "hr@example.com"
    assert normalise_indicator_value("phone", "+91 98765-43210") == "919876543210"
    assert normalise_indicator_value("brand", "Example Technologies Pvt Ltd") == "example technologies"
    assert normalise_indicator_value("ip", "not-an-ip") == ""


def test_threat_ingest_dedupes_and_match_reports_honest_state(repos):
    store = ThreatIndicatorStore(Settings(mongodb_uri="mongomock://"), repos)
    first = store.ingest(
        [
            {
                "kind": "domain",
                "value": "https://www.bad-offer.example.com/claim",
                "description": "Observed in an operator-supplied feed record.",
                "severity": 0.7,
            }
        ]
    )
    second = store.ingest(
        [
            {
                "kind": "domain",
                "value": "bad-offer.example.com",
                "description": "Same value, different spelling.",
                "severity": 0.9,
            }
        ]
    )
    assert first["ingested"] == 1
    assert second["ingested"] == 1
    assert repos.threat_indicators.count() == 1
    record = repos.threat_indicators.find_one({})
    assert record["normalized_value"] == "bad-offer.example.com"
    assert record["severity"] == 0.9
    assert record["expires_at"]

    match = store.match(["https://bad-offer.example.com/other"])
    assert match["status"] == "ok"
    assert len(match["matches"]) == 1
    assert match["indicators"][0]["name"] == "threat_indicator_match"
    assert "not proof of fraud" in match["indicators"][0]["description"]

    absent = store.match(["clean.example.com"])
    assert absent["status"] == "no_match"
    assert "does not establish legitimacy" in " ".join(absent["limitations"])


def test_expired_indicators_are_not_matched(repos):
    store = ThreatIndicatorStore(Settings(mongodb_uri="mongomock://"), repos)
    store.ingest([{"kind": "email", "value": "old@example.com"}])
    repos.threat_indicators.col.update_one(
        {"normalized_value": "old@example.com"},
        {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(days=1)}},
    )
    match = store.match(["old@example.com"])
    assert match["status"] == "no_match"


def test_empty_and_unconfigured_states(repos):
    store = ThreatIndicatorStore(Settings(mongodb_uri="mongomock://"), repos)
    assert store.match([])["status"] == "not_attempted"
    refresh = store.refresh_source("missing-feed")
    assert refresh["status"] == "not_configured"
    sources = {item["source_id"]: item for item in store.sources()}
    assert sources["operator_import"]["status"] == "configured"


def test_private_feed_url_is_rejected_without_network(repos):
    store = ThreatIndicatorStore(Settings(mongodb_uri="mongomock://"), repos)
    with pytest.raises(ValueError):
        store.register_source(source_id="bad", name="Bad Feed", url="http://127.0.0.1/feed.json")
