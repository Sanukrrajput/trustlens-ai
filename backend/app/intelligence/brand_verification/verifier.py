"""Separate entity verification from official-campaign authorisation.

A registry match can establish that a legal entity exists. It cannot establish
that a particular advertisement, giveaway, scholarship or recruiter was
authorised by that entity. This engine keeps those claims separate and only uses
the ``verified_official_campaign`` state when independent evidence of the
specific campaign is supplied by a caller that can substantiate it.

The engine performs no network requests of its own, so it can never become a
silent dependency of the web application. External evidence is obtained by the
orchestrator through consent-gated, SSRF-safe services.
"""

from __future__ import annotations

from typing import Any, Iterable

from app.intelligence import BRAND_NAMES, dedupe, iso, make_indicator, normalise_company_name

VERIFICATION_STATES = (
    "verified_company",
    "verified_official_campaign",
    "unverified_advertisement",
    "suspected_impersonation",
    "not_attempted",
)

# User-supplied screenshots, advert text and forum posts are never independent
# proof that a brand authorised a campaign.
INDEPENDENT_SOURCE_TYPES = frozenset(
    {
        "official_registry",
        "official_brand_channel",
        "independent_verification",
    }
)

BRAND_ALIASES = {
    "sbi": ("state bank of india", "statebankofindia"),
    "hdfc": ("hdfc bank",),
    "icici": ("icici bank",),
    "amazon": ("amazon india",),
    "flipkart": ("flipkart india",),
}

_IMPERSONATION_KINDS = frozenset(
    {"impersonation", "brand_impersonation", "phishing", "official_impersonation"}
)


def _normalised_brand(value: Any) -> str:
    return normalise_company_name(str(value or ""))


def _mentions_known_brand(value: Any) -> str | None:
    """Return the canonical known brand name when the claim clearly names one."""
    text = _normalised_brand(value)
    if not text:
        return None
    for brand in BRAND_NAMES:
        aliases = (brand, *BRAND_ALIASES.get(brand, ()))
        for alias in aliases:
            needle = _normalised_brand(alias)
            if needle and (text == needle or f" {needle} " in f" {text} "):
                return brand
    return None


def _trusted_campaign_evidence(evidence: Iterable[Any]) -> dict[str, Any] | None:
    for item in evidence or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("source_type") or "") not in INDEPENDENT_SOURCE_TYPES:
            continue
        if not item.get("independently_verified"):
            continue
        if not str(item.get("reference_url") or "").strip():
            continue
        return item
    return None


class BrandVerifier:
    """Produce an explainable brand/campaign verification state."""

    def verify(
        self,
        *,
        claimed_brand: str | None = None,
        campaign: dict[str, Any] | None = None,
        company_result: dict[str, Any] | None = None,
        domain_result: dict[str, Any] | None = None,
        threat_matches: list[dict[str, Any]] | None = None,
        campaign_evidence: list[dict[str, Any]] | None = None,
        consent_external_lookups: bool = False,
    ) -> dict[str, Any]:
        claimed_brand = str(claimed_brand or "").strip()
        campaign = campaign if isinstance(campaign, dict) else {}
        company_result = company_result if isinstance(company_result, dict) else {}
        domain_result = domain_result if isinstance(domain_result, dict) else {}
        threat_matches = [item for item in (threat_matches or []) if isinstance(item, dict)]
        campaign_evidence = [item for item in (campaign_evidence or []) if isinstance(item, dict)]

        evidence: list[dict[str, Any]] = []
        contradictions: list[dict[str, Any]] = []
        missing_evidence: list[str] = []
        limitations: list[str] = [
            "A verified company does not verify a specific offer, campaign, advert or recruiter.",
            "Brand names, logos and screenshots are observations, not proof of authorisation.",
        ]
        indicators: list[dict[str, Any]] = []

        if not claimed_brand and not campaign:
            result = {
                "status": "not_attempted",
                "state": "not_attempted",
                "entity_verified": False,
                "campaign_verified": False,
                "claimed_brand": "",
                "known_brand": None,
                "evidence": evidence,
                "contradictions": contradictions,
                "missing_evidence": ["No brand or campaign claim was supplied."],
                "limitations": limitations,
                "indicators": [
                    make_indicator(
                        name="brand_verification_not_attempted",
                        status="missing",
                        severity=0.0,
                        description="No brand or campaign claim was available to verify.",
                        source="brand verification",
                        confidence=0.9,
                    )
                ],
                "observed_at": iso(),
            }
            return result

        brand = claimed_brand or str(campaign.get("claimed_brand") or campaign.get("company_name") or "")
        known_brand = _mentions_known_brand(brand)
        entity_verified = company_result.get("verification_status") == "verified_with_evidence"
        trusted_evidence = _trusted_campaign_evidence(campaign_evidence)

        if entity_verified:
            evidence.append(
                {
                    "claim": "licensed registry evidence corroborates the named entity",
                    "source": "company verification",
                    "observed_at": iso(),
                    "confidence": 0.9,
                    "independently_verified": True,
                    "limitations": ["This does not authorise any particular campaign."],
                }
            )
            indicators.append(
                make_indicator(
                    name="brand_entity_verified",
                    status="supportive",
                    severity=0.0,
                    description="A licensed registry source corroborated the claimed legal entity.",
                    source="company verification",
                    confidence=0.9,
                    independently_verified=True,
                )
            )
        else:
            missing_evidence.append("No licensed registry evidence corroborated the claimed entity.")

        if trusted_evidence:
            evidence.append(
                {
                    "claim": str(trusted_evidence.get("claim") or "official campaign authorisation"),
                    "source": str(trusted_evidence.get("source") or trusted_evidence.get("source_type")),
                    "reference_url": str(trusted_evidence.get("reference_url")),
                    "observed_at": str(trusted_evidence.get("observed_at") or iso()),
                    "confidence": 0.9,
                    "independently_verified": True,
                    "limitations": ["Evidence is limited to the campaign reference supplied by the source."],
                }
            )
            indicators.append(
                make_indicator(
                    name="brand_campaign_verified",
                    status="supportive",
                    severity=0.0,
                    description="An independent source linked the named brand to this specific campaign.",
                    source=str(trusted_evidence.get("source") or "independent campaign evidence"),
                    reference_url=str(trusted_evidence.get("reference_url")),
                    confidence=0.9,
                    independently_verified=True,
                )
            )
        else:
            missing_evidence.append(
                "No independent evidence confirms that the named brand authorised this specific offer or campaign."
            )
            indicators.append(
                make_indicator(
                    name="brand_campaign_not_verified",
                    status="missing",
                    severity=0.0,
                    description="Campaign authorisation was not independently verified; this is missing evidence, not a clean result.",
                    source="brand verification",
                    confidence=0.8,
                )
            )

        impersonation_reasons: list[str] = []
        normalised_brand = _normalised_brand(brand)
        for match in threat_matches:
            kind = str(match.get("kind") or match.get("name") or "")
            matched_value = _normalised_brand(match.get("brand") or match.get("value") or match.get("normalized_value"))
            if kind in _IMPERSONATION_KINDS or (
                matched_value and normalised_brand and matched_value == normalised_brand
            ):
                description = str(match.get("description") or "Threat indicator references this brand.")
                impersonation_reasons.append(description)
                evidence.append(
                    {
                        "claim": "threat indicator references the claimed brand",
                        "source": str(match.get("source") or "threat indicator store"),
                        "value": str(match.get("value") or ""),
                        "observed_at": str(match.get("observed_at") or iso()),
                        "confidence": 0.5,
                        "independently_verified": bool(match.get("independently_verified")),
                        "limitations": ["A store match is an indicator, not proof of fraud."],
                    }
                )

        domain_indicators = domain_result.get("indicators") or []
        lookalike = next(
            (item for item in domain_indicators if isinstance(item, dict) and item.get("name") == "domain_lookalike_heuristic"),
            None,
        )
        if known_brand and lookalike and not entity_verified and not trusted_evidence:
            impersonation_reasons.append(
                f"An uncorroborated domain resembles the known brand '{known_brand}'."
            )
            limitations.append(
                "Lookalike-domain detection is a clearly labelled heuristic; similar names can be legitimate."
            )

        if impersonation_reasons:
            state = "suspected_impersonation"
            contradictions.append(
                {
                    "claim": "claimed brand identity is not independently corroborated",
                    "source": "brand verification",
                    "value": "; ".join(dedupe(impersonation_reasons)[:3]),
                    "observed_at": iso(),
                    "confidence": 0.5,
                    "limitations": ["Suspicion is not a finding of fraud."],
                }
            )
            indicators.append(
                make_indicator(
                    name="brand_impersonation_suspected",
                    status="suspicious",
                    severity=0.6,
                    description=(
                        "Brand-impersonation indicators were observed: "
                        + "; ".join(dedupe(impersonation_reasons)[:3])
                        + ". These are indicators, not proof of fraud."
                    ),
                    source="brand verification",
                    confidence=0.5,
                )
            )
        elif entity_verified and trusted_evidence:
            state = "verified_official_campaign"
        elif entity_verified:
            state = "verified_company"
        else:
            state = "unverified_advertisement"

        if not consent_external_lookups:
            limitations.append(
                "External corroboration was not attempted by the orchestrator because consent was not provided."
            )

        return {
            "status": "ok",
            "state": state,
            "entity_verified": bool(entity_verified),
            "campaign_verified": bool(trusted_evidence),
            "claimed_brand": brand,
            "known_brand": known_brand,
            "evidence": evidence,
            "contradictions": contradictions,
            "missing_evidence": missing_evidence,
            "limitations": limitations,
            "indicators": indicators,
            "observed_at": iso(),
        }


__all__ = ["BrandVerifier", "VERIFICATION_STATES"]
