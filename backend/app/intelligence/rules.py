"""Convert module output into a single, deduplicated indicator list.

Indicators are canonicalised by underlying signal so the same observation is
never counted twice just because extraction, message rules and domain rules all
noticed it.
"""

from __future__ import annotations

from typing import Any

from app.intelligence import iso, make_indicator

# Map module-specific indicator names to canonical signal names.
CANONICAL_NAMES = {
    "message_fee_demand": "payment_demand",
    "message_sensitive_data_request": "sensitive_data_request",
    "message_urgency_pressure": "urgency_pressure",
    "message_fake_offer_letter": "offer_letter_claim",
    "message_document_submission": "document_submission",
    "message_phishing_links": "phishing_link",
    "message_personal_email_sender": "personal_email_sender",
    "message_whatsapp_sms_patterns": "messaging_channel_pattern",
    "message_unverified_claims": "unverified_claim",
    "domain_recently_registered": "recently_registered_domain",
    "domain_lookalike_heuristic": "brand_lookalike_heuristic",
    "domain_threat_feed_match": "threat_feed_match",
    "tls_certificate_invalid": "tls_certificate_invalid",
    "rdap_technical_limitation": "rdap_technical_limitation",
    "tls_technical_limitation": "tls_technical_limitation",
    "virustotal_technical_limitation": "threat_feed_limitation",
    "domain_registration_date_missing": "registration_date_missing",
    "domain_not_parseable": "domain_not_parseable",
    "company_registry_confirmation": "registry_confirmation",
    "company_registry_not_confirmed": "registry_not_confirmed",
    "company_website_name_overlap": "company_website_evidence",
    "company_website_name_absent": "company_name_not_on_website",
    "company_email_domain_mismatch": "company_email_domain_mismatch",
    "company_external_verification_not_attempted": "company_verification_not_attempted",
    # Generic offer rules map onto existing canonical signals where the same
    # underlying observation is already measured, preventing double-counting.
    "offer_advance_payment": "payment_demand",
    "offer_credential_request": "sensitive_data_request",
    "offer_urgency": "urgency_pressure",
    "offer_unrealistic_claim": "unverified_claim",
    "offer_personal_channel": "messaging_channel_pattern",
    "offer_recruitment_fee": "payment_demand",
    "offer_investment_guarantee": "unverified_claim",
    # Image OCR reports observations, not authenticity. Payment/credential text
    # is merged with text-based findings so the same demand is not counted twice.
    "image_payment_request": "payment_demand",
    "image_credential_request": "sensitive_data_request",
    "threat_indicator_match": "threat_feed_match",
}


def _copy(
    raw: dict[str, Any],
    collected: dict[str, dict[str, Any]],
    *,
    category: str = "content",
) -> None:
    name = CANONICAL_NAMES.get(str(raw.get("name") or ""), str(raw.get("name") or ""))
    add(
        collected,
        name=name,
        status=str(raw.get("status") or "unverified"),
        severity=raw.get("severity", 0.1),
        description=str(raw.get("description") or ""),
        source=str(raw.get("source") or "rule"),
        reference_url=raw.get("reference_url"),
        observed_at=raw.get("observed_at"),
        confidence=raw.get("confidence", 0.5),
        independently_verified=bool(raw.get("independently_verified")),
        expires_at=raw.get("expires_at"),
        weight=raw.get("weight", 1.0),
        signal_category=str(raw.get("signal_category") or category),
    )


def add(collected: dict[str, dict[str, Any]], **spec: Any) -> None:
    """Add an indicator, merging duplicate canonical signals in place."""
    name = str(spec.pop("name", "")).strip() or "unnamed_indicator"
    indicator = make_indicator(name=name, **spec)
    existing = collected.get(name)
    if existing is None:
        collected[name] = indicator
        return
    # Keep the strongest observation but preserve both explanations briefly.
    if indicator["severity"] > existing["severity"]:
        existing["severity"] = indicator["severity"]
        existing["status"] = indicator["status"]
    existing["confidence"] = max(existing["confidence"], indicator["confidence"])
    existing["weight"] = max(existing["weight"], indicator["weight"])
    existing["independently_verified"] = existing["independently_verified"] or indicator["independently_verified"]
    if indicator["reference_url"] and not existing["reference_url"]:
        existing["reference_url"] = indicator["reference_url"]
    extra = indicator["description"]
    if extra and extra not in existing["description"]:
        existing["description"] = f"{existing['description']} Also observed: {extra}"[:1000]


def build_rule_indicators(
    *,
    extracted: dict[str, Any] | None,
    domain: dict[str, Any] | None,
    company: dict[str, Any] | None,
    message: dict[str, Any] | None,
    historical: dict[str, Any] | None,
    image: dict[str, Any] | None = None,
    brand: dict[str, Any] | None = None,
    threat: dict[str, Any] | None = None,
    offer: dict[str, Any] | None = None,
    community: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return deduplicated EvidenceIndicator-shaped dicts for all inputs."""
    collected: dict[str, dict[str, Any]] = {}
    extracted = extracted or {}
    domain = domain or {}
    company = company or {}
    message = message or {}
    historical = historical or {}
    image = image or {}
    brand = brand or {}
    threat = threat or {}
    offer = offer or {}
    community = community or {}

    payments = extracted.get("payment_demands") or []
    if payments:
        add(
            collected,
            name="payment_demand",
            status="suspicious",
            severity=0.55,
            description="Payment demand extracted from the supplied text: " + "; ".join(str(item) for item in payments[:2]),
            source="entity extraction",
            confidence=0.6,
            signal_category="content",
        )
    sensitive = extracted.get("sensitive_data_requests") or []
    if sensitive:
        add(
            collected,
            name="sensitive_data_request",
            status="suspicious",
            severity=0.55,
            description="Request for credentials or sensitive documents extracted from the text.",
            source="entity extraction",
            confidence=0.6,
            signal_category="content",
        )

    personal_emails = [
        email
        for email in (extracted.get("recruiter_emails") or [])
        if isinstance(email, str) and email.rsplit("@", 1)[-1].lower()
        in {
            "gmail.com", "yahoo.com", "yahoo.co.in", "hotmail.com", "outlook.com", "live.com",
            "icloud.com", "rediffmail.com", "protonmail.com", "aol.com", "proton.me",
        }
    ]
    if personal_emails:
        add(
            collected,
            name="personal_email_sender",
            status="unverified",
            severity=0.2,
            description="A free/personal email provider was used as a recruiter contact; this is common and not proof of fraud.",
            source="entity extraction",
            confidence=0.4,
            signal_category="content",
        )

    for raw in domain.get("indicators") or []:
        if isinstance(raw, dict):
            _copy(raw, collected, category="url")
    for raw in company.get("indicators") or []:
        if isinstance(raw, dict):
            _copy(raw, collected, category="brand")
    for raw in message.get("indicators") or []:
        if isinstance(raw, dict):
            _copy(raw, collected, category="content")
    for raw in historical.get("indicators") or []:
        if isinstance(raw, dict):
            _copy(raw, collected, category="community")
    for raw in image.get("indicators") or []:
        if isinstance(raw, dict):
            _copy(raw, collected, category="content")
    for raw in brand.get("indicators") or []:
        if isinstance(raw, dict):
            _copy(raw, collected, category="brand")
    for raw in threat.get("indicators") or []:
        if isinstance(raw, dict):
            _copy(raw, collected, category="threat")
    for raw in offer.get("indicators") or []:
        if isinstance(raw, dict):
            _copy(raw, collected, category="content")
    for raw in community.get("indicators") or []:
        if isinstance(raw, dict):
            _copy(raw, collected, category="community")

    contradictions = company.get("contradictions") or []
    if contradictions:
        descriptions = [
            str(item.get("claim") if isinstance(item, dict) else item) for item in contradictions[:3]
        ]
        add(
            collected,
            name="company_identity_inconsistency",
            status="verified_inconsistency",
            severity=0.55,
            description="Company corroboration found inconsistencies: " + "; ".join(descriptions),
            source="company verification",
            confidence=0.5,
            signal_category="brand",
        )

    counts = historical.get("historical_counts") or {}
    if isinstance(counts, dict):
        count_specs = (
            ("recruiter", "repeated_recruiter", 0.4, "The same recruiter fingerprint appeared in earlier records."),
            ("domain", "repeated_domain", 0.35, "The same domain appeared in earlier records."),
            ("payment_phrase", "repeated_payment_phrase", 0.35, "Similar payment language appeared in earlier records."),
            ("company", "repeated_company", 0.3, "The same company name appeared in earlier records."),
        )
        for key, name, base_severity, description in count_specs:
            entry = counts.get(key) or {}
            total = int(entry.get("analyses", 0) or 0) + int(entry.get("listings", 0) or 0) if isinstance(entry, dict) else int(entry or 0)
            if total > 1:
                add(
                    collected,
                    name=name,
                    status="suspicious",
                    severity=min(0.75, base_severity + 0.05 * (total - 2)),
                    description=f"{description} Observed {total} previous time(s). Repetition alone is not proof of fraud.",
                    source="historical analysis repository",
                    confidence=0.45,
                    signal_category="community",
                )

    signals = historical.get("signals") or {}
    if isinstance(signals, dict) and signals.get("shared_infrastructure_only"):
        add(
            collected,
            name="shared_infrastructure",
            status="supportive",
            severity=0.0,
            description="Shared hosting/infrastructure was observed; this is common and is explicitly not treated as evidence of fraud.",
            source="historical analysis repository",
            confidence=0.5,
            weight=0.2,
            signal_category="community",
        )

    if not domain and not company:
        add(
            collected,
            name="external_verification_missing",
            status="missing",
            severity=0.0,
            description="No domain or company intelligence was available for this analysis.",
            source="coverage check",
            confidence=0.9,
            signal_category="coverage",
        )
    if isinstance(domain, dict) and domain.get("status") in {"limited", "error", "unavailable"}:
        add(
            collected,
            name="technical_limitation",
            status="technical_limitation",
            severity=0.05,
            description="External domain checks were incomplete; absent findings should not be read as clean findings.",
            source="domain analysis",
            confidence=0.8,
            signal_category="url",
        )

    # Ensure every indicator has a valid observation timestamp even if an
    # upstream module returned a malformed value.
    for indicator in collected.values():
        indicator["observed_at"] = indicator.get("observed_at") or iso()
    return sorted(collected.values(), key=lambda item: (-item["severity"], item["name"]))


__all__ = ["build_rule_indicators"]
