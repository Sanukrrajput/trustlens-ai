"""Tests for the TrustLens explainable intelligence modules.

All network calls are mocked; these tests never contact external services.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.intelligence import EVIDENCE_STATUSES, make_indicator  # noqa: E402
from app.intelligence.anomaly import AnomalyEngine  # noqa: E402
from app.intelligence.company_verification import CompanyVerifier  # noqa: E402
from app.intelligence.domain_analysis import DomainAnalyser  # noqa: E402
from app.intelligence.extraction import extract_entities  # noqa: E402
from app.intelligence.message_analysis import MessageAnalyser  # noqa: E402
from app.intelligence.offer_rules import OFFER_CATEGORIES, build_offer_indicators  # noqa: E402
from app.intelligence.rules import build_rule_indicators  # noqa: E402
from app.intelligence.url_scanning import SafeURLFetcher  # noqa: E402
from app.intelligence.url_scanning import safe_fetch as safe_fetch_module  # noqa: E402
from app.intelligence.domain_analysis import analyser as domain_analyser_module  # noqa: E402


def settings(**overrides):
    values = {
        "rdap_enabled": True,
        "dns_enabled": True,
        "tls_enabled": True,
        "virustotal_api_key": "",
        "google_safebrowsing_api_key": "",
        "google_webrisk_api_key": "",
        "mca_api_url": "",
        "mca_api_key": "",
        "mca_require_consent": True,
        "max_fetch_bytes": 262_144,
        "fetch_timeout_seconds": 2.0,
        "max_redirects": 4,
        "domain_refresh_interval_hours": 24,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeResponse:
    def __init__(self, status=200, headers=None, body=b""):
        self.status = status
        self._headers = list((headers or {}).items())
        self._body = body
        self._sent = False

    def getheaders(self):
        return self._headers

    def read(self, amount):
        if self._sent:
            return b""
        self._sent = True
        return self._body[:amount]


class FakeConnection:
    def __init__(self, responses, certificate=None):
        self.responses = list(responses)
        self.calls = []
        self.closed = False
        self.sock = SimpleNamespace(getpeercert=lambda: certificate) if certificate else None

    def request(self, method, path, headers=None):
        self.calls.append({"method": method, "path": path, "headers": headers or {}})

    def getresponse(self):
        return self.responses.pop(0)

    def close(self):
        self.closed = True


def test_extract_entities_legitimate_text():
    text = (
        "Acme Technologies Pvt Ltd is hiring a Software Engineer in Pune. "
        "Salary: ₹8-12 LPA. Contact careers@acme.example.com for details."
    )
    entities = extract_entities(text)
    assert entities["company_names"]
    assert any("acme" in name.lower() for name in entities["company_names"])
    assert any("software engineer" in title.lower() for title in entities["job_titles"])
    assert entities["salary"] and "8" in entities["salary"]
    assert "Pune" in entities["locations"]
    assert entities["recruiter_emails"] == ["careers@acme.example.com"]
    assert entities["company_fingerprint"]
    assert entities["payment_demands"] == []
    assert entities["text_stats"]["word_count"] > 10


def test_extract_entities_fraudulent_text():
    text = (
        "URGENT: Pay ₹5000 registration fee via UPI to hr.jobs@gmail.com. "
        "Share OTP and Aadhaar card now. Call +91 98765 43210. "
        "See https://bit.ly/offer123"
    )
    entities = extract_entities(text)
    assert entities["payment_demands"]
    assert entities["sensitive_data_requests"]
    assert entities["phone_numbers"]
    assert any("bit.ly" in url for url in entities["urls"])
    assert "gmail.com" not in entities["domain_candidates"]
    assert "bit.ly" in entities["domain_candidates"]


def test_extract_entities_ambiguous_text():
    entities = extract_entities("Maybe call me later.")
    assert entities["company_names"] == []
    assert entities["company_fingerprint"] == ""
    assert entities["salary"] is None
    assert entities["payment_demands"] == []
    assert entities["text_stats"]["word_count"] <= 5


def test_message_analyser_legitimate_text_is_not_accusatory():
    text = (
        "Hi Rahul, please find the job description for Software Engineer at Acme Technologies "
        "in Pune. Salary ₹8 LPA. Send your CV to careers@acme.example.com."
    )
    result = MessageAnalyser().analyse(text, channel="email", sender="hr@acme.example.com")
    assert result["status"] == "completed"
    assert not any(item["status"] == "confirmed_malicious" for item in result["indicators"])
    lowered = result["summary"].lower()
    assert "no conclusion" in lowered or "not proof" in lowered or "no strong" in lowered
    assert result["missing_evidence"]


def test_message_analyser_fraudulent_text():
    text = (
        "URGENT! You are selected. Pay ₹5000 registration fee via UPI to hr-verify@gmail.com "
        "and share OTP and Aadhaar card now. Offer letter attached: bit.ly/offer123"
    )
    result = MessageAnalyser().analyse(text, channel="whatsapp", sender="hr-verify@gmail.com")
    assert result["signals"]["fee_demand"]["detected"]
    assert result["signals"]["sensitive_data_request"]["detected"]
    assert result["signals"]["urgency_pressure"]["detected"]
    assert result["signals"]["phishing_links"]["detected"]
    assert result["signals"]["personal_email_sender"]["detected"]
    assert len(result["indicators"]) >= 4
    assert "Several patterns" in result["summary"]


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/admin",
        "http://127.0.0.1:80/admin",
        "http://[::1]/admin",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://user:pass@example.com/",
        "file:///etc/passwd",
        "ftp://example.com/file",
        "http://example.com:8080/",
        "http://2130706433/",
    ],
)
def test_ssrf_rejects_unsafe_urls_without_network(url):
    def fail(*args, **kwargs):
        raise AssertionError("network/DNS call must not be attempted for an invalid URL")

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(safe_fetch_module.socket, "getaddrinfo", fail)
        monkeypatch.setattr(SafeURLFetcher, "_open_connection", fail)
        result = SafeURLFetcher(settings()).fetch(url)
    finally:
        monkeypatch.undo()
    assert result["status"] == "blocked", result
    assert result["errors"]


def test_ssrf_rejects_dns_answers_that_are_private(monkeypatch):
    monkeypatch.setattr(
        safe_fetch_module.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("10.20.30.40", 443))],
    )
    result = SafeURLFetcher(settings()).fetch("https://public.example.com/")
    assert result["status"] == "blocked"
    assert "non-public" in " ".join(result["errors"])


def test_safe_redirect_to_private_ip_is_blocked(monkeypatch):
    redirect = FakeResponse(
        302,
        {"Location": "http://127.0.0.1/admin", "Content-Type": "text/html"},
    )
    connection = FakeConnection([redirect])
    monkeypatch.setattr(
        safe_fetch_module.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )
    monkeypatch.setattr(SafeURLFetcher, "_open_connection", lambda self, scheme, host, port, ip: connection)

    result = SafeURLFetcher(settings()).fetch("https://public.example.com/")
    assert result["status"] == "blocked"
    assert result["redirect_chain"] == ["http://127.0.0.1/admin"]
    assert len(connection.calls) == 1, "the private redirect target must never be fetched"


def test_safe_redirect_to_hostname_resolving_private_is_blocked(monkeypatch):
    seen_hosts = []

    def fake_getaddrinfo(host, port, **kwargs):
        seen_hosts.append(host)
        if "internal.example" in host:
            return [(2, 1, 6, "", ("192.168.50.5", port))]
        return [(2, 1, 6, "", ("93.184.216.34", port))]

    redirect = FakeResponse(302, {"Location": "https://internal.example/admin", "Content-Type": "text/html"})
    connection = FakeConnection([redirect])
    monkeypatch.setattr(safe_fetch_module.socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(SafeURLFetcher, "_open_connection", lambda self, scheme, host, port, ip: connection)

    result = SafeURLFetcher(settings()).fetch("https://public.example.com/")
    assert result["status"] == "blocked"
    assert "internal.example" in seen_hosts
    assert len(connection.calls) == 1


def test_successful_fetch_returns_structured_result(monkeypatch):
    certificate = {
        "subject": ((("commonName", "example.com"),),),
        "issuer": ((("organizationName", "Test CA"),),),
        "notBefore": "Jan  1 00:00:00 2025 GMT",
        "notAfter": "Jan  1 00:00:00 2030 GMT",
        "subjectAltName": (("DNS", "example.com"),),
        "serialNumber": "01",
    }
    response = FakeResponse(
        200,
        {"Content-Type": "text/html; charset=utf-8", "Server": "test", "Set-Cookie": "secret=1"},
        b"<html><body>Hello</body></html>",
    )
    connection = FakeConnection([response], certificate=certificate)
    monkeypatch.setattr(
        safe_fetch_module.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )
    monkeypatch.setattr(SafeURLFetcher, "_open_connection", lambda self, scheme, host, port, ip: connection)

    result = SafeURLFetcher(settings()).fetch("https://example.com/page?q=1")
    assert result["status"] == "ok"
    assert result["http_status"] == 200
    assert result["final_url"] == "https://example.com/page?q=1"
    assert "Hello" in result["body_preview"]
    assert result["headers_subset"]["content-type"].startswith("text/html")
    assert "set-cookie" not in result["headers_subset"]
    assert result["certificate"]["san"] == ["example.com"]
    assert "Host" in connection.calls[0]["headers"]


def test_pinned_https_connection_preserves_sni(monkeypatch):
    captured = {}

    class FakeSocket:
        def settimeout(self, value):
            captured["timeout"] = value

        def connect(self, address):
            captured["address"] = address

    class FakeWrappedSocket:
        def getpeercert(self):
            return {}

    class FakeContext:
        def wrap_socket(self, sock, server_hostname=None):
            captured["sni"] = server_hostname
            return FakeWrappedSocket()

    monkeypatch.setattr(safe_fetch_module.socket, "socket", lambda family, kind: FakeSocket())
    connection = safe_fetch_module._PinnedHTTPSConnection(
        "example.com", 443, pinned_ip="93.184.216.34", timeout=3, context=FakeContext()
    )
    connection.connect()
    assert captured["address"][0] == "93.184.216.34"
    assert captured["sni"] == "example.com"


def test_unconfigured_external_apis_report_honest_status(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("external API must not be called without credentials")

    monkeypatch.setattr(domain_analyser_module.requests, "get", fail)
    monkeypatch.setattr(domain_analyser_module.requests, "post", fail)
    analyser = DomainAnalyser(settings(rdap_enabled=False, dns_enabled=False, tls_enabled=False))
    result = analyser.analyse("example.com")
    for name in ("virustotal", "safe_browsing", "web_risk"):
        assert result["threat_intel"][name]["status"] == "not_configured"
        assert result["threat_intel"][name]["confidence"] == 0.0
    assert result["rdap"]["status"] == "disabled"
    assert result["dns"]["status"] == "disabled"
    assert result["tls"]["status"] == "disabled"
    assert not any(item["status"] == "confirmed_malicious" for item in result["indicators"])


def test_lookalike_domain_is_heuristic_not_proof():
    analyser = DomainAnalyser(settings(rdap_enabled=False, dns_enabled=False, tls_enabled=False))
    result = analyser.analyse("https://sbi-secure-login.in")
    brands = [match["brand"] for match in result["lookalikes"]["data"]["matches"]]
    assert "sbi" in brands
    assert "HEURISTIC ONLY" in " ".join(result["lookalikes"]["limitations"])
    assert any(item["name"] == "domain_lookalike_heuristic" for item in result["indicators"])
    assert not any(item["status"] == "confirmed_malicious" for item in result["indicators"])


def test_rule_indicators_are_complete_and_deduplicated():
    extracted = {
        "payment_demands": ["Pay ₹5000 registration fee via UPI"],
        "sensitive_data_requests": ["Share OTP"],
        "recruiter_emails": ["hr@gmail.com"],
    }
    domain = {
        "status": "ok",
        "indicators": [
            make_indicator(
                name="domain_recently_registered",
                status="suspicious",
                severity=0.35,
                description="new domain",
                source="rdap",
                confidence=0.6,
            )
        ],
    }
    company = {
        "contradictions": [{"claim": "name absent from website", "source": "website"}],
        "indicators": [],
    }
    message = {
        "indicators": [
            make_indicator(
                name="message_fee_demand",
                status="suspicious",
                severity=0.5,
                description="fee demand in message",
                source="rules",
                confidence=0.7,
            )
        ]
    }
    historical = {
        "historical_counts": {"recruiter": {"analyses": 3, "listings": 0, "available": True}},
        "indicators": [],
    }

    indicators = build_rule_indicators(
        extracted=extracted,
        domain=domain,
        company=company,
        message=message,
        historical=historical,
    )
    names = [item["name"] for item in indicators]
    assert len(names) == len(set(names))
    assert "payment_demand" in names
    assert "message_fee_demand" not in names
    assert "recently_registered_domain" in names
    assert "company_identity_inconsistency" in names
    for item in indicators:
        assert set(item) >= {
            "name", "status", "severity", "description", "source", "reference_url",
            "observed_at", "confidence", "independently_verified", "expires_at", "weight",
        }
        assert item["status"] in EVIDENCE_STATUSES
        assert 0.0 <= item["severity"] <= 1.0
        assert 0.0 <= item["confidence"] <= 1.0
    assert [item["severity"] for item in indicators] == sorted(
        (item["severity"] for item in indicators), reverse=True
    )


def test_company_verifier_requires_consent(monkeypatch):
    verifier = CompanyVerifier(settings())

    def fail(*args, **kwargs):
        raise AssertionError("external lookup must not be attempted without consent")

    monkeypatch.setattr(verifier.fetcher, "fetch", fail)
    monkeypatch.setattr(verifier.domain_analyser, "analyse", fail)
    result = verifier.verify("Acme Technologies", "https://acme.example.com/", consent_external=False)
    assert result["verification_status"] == "not_attempted"
    assert result["evidence"] == []
    assert result["registry"]["status"] == "not_attempted"
    assert any("consent" in item.lower() for item in result["limitations"])


def test_company_verifier_uses_consented_website_evidence(monkeypatch):
    verifier = CompanyVerifier(settings())
    markup = (
        "<html><head><title>Acme Technologies - Careers</title></head>"
        "<body><p>Acme Technologies Pvt Ltd is hiring. Contact jobs@acme.example.com.</p></body></html>"
    )
    monkeypatch.setattr(
        verifier.fetcher,
        "fetch",
        lambda url: {
            "status": "ok",
            "final_url": "https://acme.example.com/",
            "http_status": 200,
            "body_preview": markup,
            "errors": [],
            "limitations": [],
        },
    )
    monkeypatch.setattr(
        verifier.domain_analyser,
        "analyse",
        lambda url: {"status": "ok", "indicators": [], "signals": {"domain_age_days": {"value": 400}}},
    )
    result = verifier.verify(
        "Acme Technologies Pvt Ltd",
        "https://acme.example.com/",
        consent_external=True,
    )
    assert result["verification_status"] == "partial"
    assert result["evidence"]
    assert result["registry"]["status"] == "not_configured"
    assert "no official public api" in " ".join(result["registry"]["limitations"]).lower()
    assert result["website"]["overlap"]["ratio"] == 1.0


def test_anomaly_engine_without_repos_is_limited():
    engine = AnomalyEngine(settings())
    result = engine.assess(
        {
            "recruiter_email": "hr@example.com",
            "extracted": {"domain_candidates": ["example.com"], "payment_demands": ["fee"]},
        }
    )
    assert result["status"] == "limited"
    for key in ("recruiter", "domain", "payment_phrase", "company"):
        assert result["historical_counts"][key]["analyses"] == 0
        assert result["historical_counts"][key]["available"] is False
    assert result["model"]["status"] == "not_available"
    assert any("repository" in item for item in result["limitations"])


def test_offer_rules_report_indicators_without_a_verdict():
    text = (
        "Congratulations, you have won a guaranteed prize! Share with 10 friends "
        "and pay a processing fee to claim your reward. Share your OTP to confirm. Act now, today only."
    )
    indicators = build_offer_indicators(text, "giveaway")
    names = {item["name"] for item in indicators}
    assert {"offer_advance_payment", "offer_urgency", "offer_credential_request", "offer_giveaway_share_manipulation"} <= names
    assert all(item["source"] == "offer_rules" for item in indicators)
    assert all(item["independently_verified"] is False for item in indicators)
    assert all("not proof of fraud" in item["description"] for item in indicators)
    assert all(item["status"] in EVIDENCE_STATUSES for item in indicators)


def test_offer_rules_do_not_flag_a_benign_offer():
    indicators = build_offer_indicators(
        "Community library book sale this Saturday. Books cost fifty rupees and all proceeds support the reading room.",
        "promotion",
    )
    assert indicators == []


def test_offer_categories_are_closed_and_category_specific():
    assert set(OFFER_CATEGORIES) == {
        "advertisement", "giveaway", "scholarship", "investment",
        "recruitment", "promotion", "other",
    }
    scholarship = build_offer_indicators("Pay a scholarship processing fee to release your award.", "scholarship")
    assert any(item["name"] == "offer_scholarship_fee" for item in scholarship)
    # An unknown category must fall back safely, not raise.
    assert build_offer_indicators("A normal promotional message.", "unknown") == []
