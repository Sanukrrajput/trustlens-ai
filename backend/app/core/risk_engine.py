"""Explainable, verification-aware risk scoring across five signal categories.

Why thresholds and boosts are calibrated this way
-------------------------------------------------
The score is *not* a model confidence value and *not* a calibrated fraud
probability. It is a weighted blend of five evidence categories whose weights
come from ``settings.risk_weights`` and are renormalised over whichever sources
are actually available. A missing lookup cannot be mistaken for a clean lookup.

Initial category weights (specification split):

* ``content``   30% - offer/message language, ML output, extracted text and OCR observations
* ``url``       25% - URL structure, DNS/RDAP/TLS and domain reputation
* ``brand``     25% - company, brand and campaign verification
* ``threat``    10% - threat-indicator store and configured feeds
* ``community`` 10% - historical patterns and later community reports

Within one category, the strongest available sub-signal is used rather than
summing overlapping detections, so the same payment demand extracted twice is
not counted twice. Two explicit boosts encode the asymmetry between weak and
strong evidence: +25 for an independently verified confirmed-malicious or
verified-inconsistency indicator, and +28 for confirmed malicious domain or
company reputation. Boosts are applied to the available-evidence score and
capped at 100.

Category bands are deliberately conservative and configurable:

* 0-19   Low observed risk       - only weak/neutral signals, or very little evidence
* 20-39  Limited warning signals - one or two unverified anomalies
* 40-59  Moderate risk           - at least one meaningful signal
* 60-79  High risk               - corroboration or a confirmed reputation signal
* 80-100 Critical risk indicators - multiple independent strong signals

Low coverage sets ``inconclusive=True`` and suppresses reassuring language while
still returning a score computed only from the evidence that exists.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any

from app.core.config import Settings
from app.schemas import RiskAssessment

SIGNAL_CATEGORIES: tuple[str, ...] = ("content", "url", "brand", "threat", "community")
DEFAULT_WEIGHTS: dict[str, float] = {
    "content": 0.30,
    "url": 0.25,
    "brand": 0.25,
    "threat": 0.10,
    "community": 0.10,
}
DEFAULT_BANDS: tuple[int, int, int, int] = (19, 39, 59, 79)

CATEGORY_LABELS: tuple[str, ...] = (
    "Low observed risk",
    "Limited warning signals",
    "Moderate risk",
    "High risk",
    "Critical risk indicators",
)

_STATUS_MULTIPLIER: dict[str, float] = {
    "confirmed_malicious": 1.0,
    "verified_inconsistency": 0.9,
    "suspicious": 0.55,
    "unverified": 0.22,
    "technical_limitation": 0.12,
    "missing": 0.05,
    "supportive": 0.0,
}

_MALICIOUS_WORDS = {"malicious", "phishing", "blacklisted", "fraud", "fraudulent", "spam"}
_GOOD_WORDS = {"clean", "legitimate", "trusted", "safe", "verified"}
_UNAVAILABLE_STATES = {"not_attempted", "not_configured", "unavailable", "error", "disabled", "pending"}
_LOW_COVERAGE_THRESHOLD = 0.35


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return float(min(max(float(value), low), high))


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _section_state(data: Any) -> str:
    section = _as_dict(data)
    return str(
        section.get("status")
        or section.get("verification_status")
        or section.get("state")
        or ""
    ).strip().lower()


def _section_available(data: Any) -> bool:
    """Return False when a module explicitly reports that it did not check."""
    section = _as_dict(data)
    return bool(section) and _section_state(section) not in _UNAVAILABLE_STATES


def _indicator_category(indicator: Any) -> str:
    value = str(_as_dict(indicator).get("signal_category") or "content")
    return value if value in SIGNAL_CATEGORIES else "content"


def _band_limits(settings: Any) -> tuple[int, int, int, int]:
    bands = getattr(settings, "risk_bands", None)
    if isinstance(bands, (tuple, list)) and len(bands) == 4:
        try:
            candidate = tuple(int(value) for value in bands)
            if sorted(candidate) == list(candidate) and all(0 <= value <= 100 for value in candidate):
                return candidate  # type: ignore[return-value]
        except (TypeError, ValueError):
            pass
    return DEFAULT_BANDS


def _categorise(score: int, settings: Any | None = None) -> str:
    low, limited, moderate, high = _band_limits(settings) if settings is not None else DEFAULT_BANDS
    if score <= low:
        return CATEGORY_LABELS[0]
    if score <= limited:
        return CATEGORY_LABELS[1]
    if score <= moderate:
        return CATEGORY_LABELS[2]
    if score <= high:
        return CATEGORY_LABELS[3]
    return CATEGORY_LABELS[4]


def _weights(settings: Any) -> dict[str, float]:
    raw = getattr(settings, "risk_weights", None)
    if not isinstance(raw, Mapping) or not raw:
        raw = dict(DEFAULT_WEIGHTS)
    cleaned = {
        name: max(0.0, _number(raw.get(name, DEFAULT_WEIGHTS[name]), DEFAULT_WEIGHTS[name]))
        for name in SIGNAL_CATEGORIES
    }
    total = sum(cleaned.values()) or 1.0
    return {name: value / total for name, value in cleaned.items()}


def _ml_component(predictions: list[dict[str, Any]]) -> tuple[float, float, list[str]]:
    trusted: list[tuple[dict[str, Any], float]] = []
    evidence: list[str] = []
    for raw in predictions or []:
        prediction = _as_dict(raw)
        if not prediction:
            continue
        name = str(prediction.get("model_name", "unknown"))
        trust = 0.45 if name.endswith("_rule_fallback") else 1.0
        if str(prediction.get("prediction", "")).lower() == "inconclusive":
            trust *= 0.5
        if any("synthetic" in str(item).lower() for item in prediction.get("limitations", [])):
            trust *= 0.6
        trusted.append((prediction, trust))
        evidence.append(
            f"Model {name} reported an uncalibrated risk score of "
            f"{_clamp(_number(prediction.get('fraud_probability'))) :.2f} "
            f"({'rule fallback, low trust' if trust < 0.9 else 'approved model'})."
        )
    if not trusted:
        return 0.0, 0.0, []
    weighted = sum(_clamp(_number(row.get("fraud_probability"))) * trust for row, trust in trusted)
    trust_total = sum(trust for _, trust in trusted) or 1.0
    mean_probability = weighted / trust_total
    strongest = max(_clamp(_number(row.get("fraud_probability"))) * trust for row, trust in trusted)
    score = _clamp(0.65 * strongest + 0.35 * mean_probability)
    coverage = _clamp(sum(trust for _, trust in trusted) / len(trusted))
    return score, coverage, evidence[:3]


def _rules_component(indicators: list[dict[str, Any]]) -> tuple[float, float, list[str], bool]:
    positive = 0.0
    supportive = 0.0
    ranked: list[tuple[float, str]] = []
    confirmed_verified = False
    for raw in indicators or []:
        indicator = _as_dict(raw)
        if not indicator:
            continue
        status = str(indicator.get("status", "unverified")).lower()
        severity = _clamp(_number(indicator.get("severity", 0.0)))
        confidence = _clamp(_number(indicator.get("confidence", 0.5)))
        weight = _clamp(_number(indicator.get("weight", 1.0)), 0.0, 2.0)
        verified = _flag(indicator.get("independently_verified"))
        if status in {"confirmed_malicious", "verified_inconsistency"} and verified:
            confirmed_verified = True
        if status == "supportive":
            supportive += severity * confidence * 0.35
            continue
        multiplier = _STATUS_MULTIPLIER.get(status, 0.22)
        verified_boost = 1.8 if verified else 1.0
        contribution = severity * confidence * weight * multiplier * verified_boost
        if contribution <= 0:
            continue
        positive += contribution
        name = str(indicator.get("name", "unnamed indicator"))
        ranked.append(
            (
                contribution,
                f"{'Independently verified ' if verified else ''}{status.replace('_', ' ')} "
                f"indicator '{name}' (severity {severity:.2f}, confidence {confidence:.2f}).",
            )
        )
    if not ranked and supportive <= 0:
        return 0.0, 0.0, [], confirmed_verified
    score = _clamp((1.0 - math.exp(-positive / 0.65)) - supportive)
    ranked.sort(reverse=True)
    return score, 1.0, [text for _, text in ranked[:3]], confirmed_verified


def _domain_component(domain: dict[str, Any]) -> tuple[float, float, list[str], bool]:
    data = _as_dict(domain)
    if not _section_available(data):
        return 0.0, 0.0, [], False
    risk = 0.0
    evidence: list[str] = []
    malicious = False
    reputation = str(data.get("reputation", data.get("status", ""))).strip().lower()
    if reputation in _MALICIOUS_WORDS or _flag(data.get("blacklisted")) or _flag(data.get("malicious")):
        risk = max(risk, 0.95)
        malicious = True
        evidence.append("Domain reputation is confirmed malicious or blacklisted by an upstream source.")
    elif reputation in _GOOD_WORDS:
        risk = min(risk, 0.15)

    if "reputation_score" in data or "trust_score" in data:
        raw_score = _number(data.get("reputation_score", data.get("trust_score")), 0.5)
        normalised = raw_score / 100.0 if raw_score > 1.0 else raw_score
        risk = max(risk, _clamp(1.0 - normalised))
        evidence.append(f"Domain reputation/trust score is {normalised:.2f} (1.0 is best).")

    age = _number(data.get("domain_age_days", data.get("age_days")), -1.0)
    if age >= 0:
        if age < 30:
            risk = max(risk, 0.75)
        elif age < 90:
            risk = max(risk, 0.45)
        elif age < 365:
            risk = max(risk, 0.20)
        evidence.append(f"Domain age is {int(age)} days.")

    warnings = _number(data.get("warnings", data.get("threat_count")), 0.0)
    if warnings > 0:
        risk = max(risk, min(1.0, warnings * 0.3))
        evidence.append(f"{int(warnings)} security warning(s) were reported for the domain.")

    if "tls_valid" in data and _flag(data.get("tls_valid")) is False:
        risk = _clamp(risk + 0.1)

    if _flag(data.get("verified")) or _flag(data.get("legitimate")):
        risk *= 0.4

    if not evidence:
        evidence.append("Domain intelligence was supplied but contained no recognised risk fields.")
    return _clamp(risk), 1.0, evidence[:3], malicious


def _company_component(company: dict[str, Any]) -> tuple[float, float, list[str], bool]:
    data = _as_dict(company)
    if not _section_available(data):
        return 0.0, 0.0, [], False
    risk = 0.0
    evidence: list[str] = []
    malicious = False
    if _flag(data.get("blacklisted")) or _flag(data.get("fraud_reported")):
        risk = max(risk, 0.9)
        malicious = True
        evidence.append("Company is blacklisted or has a reported fraud record.")
    reports = max(0.0, _number(data.get("reported_scams", data.get("fraud_reports")), 0.0))
    if reports > 0:
        risk = max(risk, min(1.0, reports * 0.35))
        evidence.append(f"{int(reports)} fraud/scam report(s) linked to the company.")
    inconsistencies = max(0.0, _number(data.get("inconsistencies", data.get("mismatches")), 0.0))
    if inconsistencies > 0:
        risk = max(risk, min(1.0, inconsistencies * 0.3))
        evidence.append(f"{int(inconsistencies)} company-detail inconsistency/ies were found.")
    if _flag(data.get("name_mismatch")):
        risk = max(risk, 0.55)
        evidence.append("Company name does not match the registered entity.")
    years = _number(data.get("years_active", data.get("company_age_years")), -1.0)
    if 0 <= years < 1:
        risk = max(risk, 0.45)
        evidence.append("Company appears to be less than one year old.")
    status = str(data.get("registration_status", data.get("mca_status", ""))).strip().lower()
    if status and status not in {"active", "registered", "verified", "operating"}:
        risk = max(risk, 0.4)
        evidence.append(f"Corporate registration status is '{status}'.")
    if _flag(data.get("verified")) or _flag(data.get("registration_verified")):
        risk *= 0.35
    if not evidence:
        evidence.append("Company intelligence was supplied but contained no recognised risk fields.")
    return _clamp(risk), 1.0, evidence[:3], malicious


def _historical_component(historical: dict[str, Any]) -> tuple[float, float, list[str]]:
    data = _as_dict(historical)
    if not _section_available(data):
        return 0.0, 0.0, []
    risk = 0.0
    evidence: list[str] = []
    if _flag(data.get("repeat_offender")) or _flag(data.get("known_scammer")):
        risk = max(risk, 0.95)
        evidence.append("Sender/entity is flagged as a repeat offender in historical records.")
    for key in ("previous_reports", "fraud_reports", "prior_high_risk", "similar_pattern_count"):
        count = max(0.0, _number(data.get(key), 0.0))
        if count > 0:
            risk = max(risk, min(1.0, count * 0.35))
            evidence.append(f"{int(count)} historical signal(s) under '{key}'.")
    age = _number(data.get("account_age_days"), -1.0)
    if 0 <= age < 30:
        risk = max(risk, 0.45)
        evidence.append("Sender account is newer than 30 days.")
    if not evidence:
        # An empty history check is not a clean result. Record no coverage so it
        # cannot renormalise the score downwards as if safety had been proven.
        return 0.0, 0.0, []
    return _clamp(risk), 1.0, evidence[:3]


def _message_component(message: dict[str, Any]) -> tuple[float, float, list[str]]:
    data = _as_dict(message)
    if not data:
        return 0.0, 0.0, []
    risk = 0.0
    evidence: list[str] = []
    if _flag(data.get("payment_demand")):
        risk = max(risk, 0.85)
        evidence.append("Message demands a payment or fee from the recipient.")
    if _flag(data.get("sensitive_data_request")):
        risk = max(risk, 0.85)
        evidence.append("Message requests sensitive personal or banking data.")
    for key in ("urgency_score", "channel_risk", "grammar_risk", "odd_hour"):
        value = _number(data.get(key), -1.0)
        if 0 <= value <= 1.0 and value > 0:
            risk = max(risk, value * 0.7)
            evidence.append(f"Message '{key}' is {value:.2f}.")
    shorteners = max(0.0, _number(data.get("link_shortener_count"), 0.0))
    if shorteners > 0:
        risk = max(risk, min(1.0, shorteners * 0.3))
        evidence.append(f"{int(shorteners)} shortened link(s) in the message.")
    if _flag(data.get("sender_domain_mismatch")):
        risk = max(risk, 0.6)
        evidence.append("Sender domain does not match the claimed organisation domain.")
    attachments = max(0.0, _number(data.get("attachment_count"), 0.0))
    if attachments > 0:
        risk = _clamp(risk + min(attachments, 3) * 0.08)
        evidence.append(f"Message contains {int(attachments)} attachment(s).")
    if not evidence:
        evidence.append("Message intelligence was supplied but contained no recognised risk fields.")
    return _clamp(risk), 1.0, evidence[:3]


def _strongest(*pairs: tuple[float, float]) -> tuple[float, float]:
    """Combine overlapping sub-signals without double-counting them."""
    usable = [pair for pair in pairs if pair[1] > 0]
    if not usable:
        return 0.0, 0.0
    return max(value for value, _ in usable), 1.0


def _weights_version(weights: dict[str, float], bands: tuple[int, int, int, int]) -> str:
    payload = json.dumps(
        {"weights": weights, "bands": bands},
        sort_keys=True,
        separators=(",", ":"),
    )
    return "w2-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _actions(score: int, inconclusive: bool, evidence: list[str], coverage: float) -> list[str]:
    actions: list[str] = []
    if inconclusive:
        actions.append(
            f"Treat this result as inconclusive: only {coverage:.0%} of signal categories were available. "
            "Collect missing evidence before making a decision."
        )
    joined = " ".join(evidence).lower()
    if score >= 60:
        actions.extend(
            [
                "Do not transfer money, buy gift cards, or share OTPs, CVV or bank details.",
                "Escalate to a human fraud reviewer and preserve the offer, advert and message history.",
            ]
        )
    elif score >= 40:
        actions.extend(
            [
                "Verify the named organisation through its own website and an independent corporate registry.",
                "Insist on a verifiable, official channel before sharing identity documents or money.",
            ]
        )
    else:
        actions.append("Continue standard verification and retain the offer and communications for the record.")
    if score >= 80:
        actions.append("Report the posting and sender to the platform and the relevant authority.")
    if "payment" in joined or "fee" in joined:
        actions.append("Treat unexplained advance payments, fees or gift-card demands as a warning sign.")
    if "sensitive" in joined or "bank" in joined:
        actions.append("Never provide full banking credentials or one-time passwords to an unverified offer.")
    return list(dict.fromkeys(actions))


def score_risk(
    *,
    ml_predictions: list[dict],
    indicators: list[dict],
    domain: dict | None,
    company: dict | None,
    historical: dict | None,
    message: dict | None,
    settings: Settings,
    image: dict | None = None,
    brand: dict | None = None,
    threat: dict | None = None,
) -> dict:
    """Combine available evidence into a :class:`RiskAssessment` dictionary.

    The returned dictionary validates against ``app.schemas.RiskAssessment`` and
    is therefore safe to pass straight to API serialisation. ``image`` shares the
    content category with text; ``brand`` shares brand with company verification;
    ``threat`` is the tenth-percent threat-indicator category.
    """
    weights = _weights(settings)
    bands = _band_limits(settings)

    grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in SIGNAL_CATEGORIES}
    for indicator in indicators or []:
        grouped[_indicator_category(indicator)].append(_as_dict(indicator))

    rule_results: dict[str, tuple[float, float, list[str], bool]] = {}
    for name in SIGNAL_CATEGORIES:
        rule_results[name] = _rules_component(grouped[name])

    ml_score, ml_coverage, ml_evidence = _ml_component(ml_predictions or [])
    message_score, message_coverage, message_evidence = _message_component(message)
    domain_score, domain_coverage, domain_evidence, domain_malicious = _domain_component(domain)
    company_score, company_coverage, company_evidence, company_malicious = _company_component(company)
    history_score, history_coverage, history_evidence = _historical_component(historical)

    # The image/OCR engine is already folded into content indicators by the
    # orchestrator. Passing it here only adds its honest status to coverage when
    # OCR actually produced observations.
    image_available = _section_available(image) and _section_state(image) == "ok"
    # An unverified advert or an empty/no-match lookup is *not* a clean result.
    # Only a state that actually changes confidence in the identity, or an
    # indicator produced by the engine, gives the brand/threat category coverage.
    brand_available = _section_available(brand) and _section_state(brand) in {
        "verified_company",
        "verified_official_campaign",
        "suspected_impersonation",
    }
    threat_checked = _section_available(threat) and _section_state(threat) in {
        "ok",
        "no_match",
        "not_configured",
        "matched",
    }

    content_score, content_coverage = _strongest(
        (ml_score, ml_coverage),
        (message_score, message_coverage),
        (rule_results["content"][0], rule_results["content"][1]),
        (0.0, 1.0 if image_available else 0.0),
    )
    url_score, url_coverage = _strongest(
        (domain_score, domain_coverage),
        (rule_results["url"][0], rule_results["url"][1]),
    )
    brand_score, brand_coverage = _strongest(
        (company_score, company_coverage),
        (rule_results["brand"][0], rule_results["brand"][1]),
        (0.0, 1.0 if brand_available else 0.0),
    )
    threat_score, threat_coverage = _strongest(
        (rule_results["threat"][0], rule_results["threat"][1]),
    )
    community_score, community_coverage = _strongest(
        (history_score, history_coverage),
        (rule_results["community"][0], rule_results["community"][1]),
    )

    component_scores = {
        "content": content_score,
        "url": url_score,
        "brand": brand_score,
        "threat": threat_score,
        "community": community_score,
    }
    coverage_by_category = {
        "content": content_coverage,
        "url": url_coverage,
        "brand": brand_coverage,
        "threat": threat_coverage,
        "community": community_coverage,
    }

    available = [name for name in SIGNAL_CATEGORIES if coverage_by_category[name] > 0]
    weight_total = sum(weights[name] for name in available)
    if not available or weight_total <= 0:
        base_score = 0.0
        coverage = 0.0
    else:
        coverage = _clamp(sum(weights[name] for name in available))
        weighted = sum(weights[name] * component_scores[name] for name in available) / weight_total
        base_score = 100.0 * weighted

    confirmed_verified = any(result[3] for result in rule_results.values())
    malicious_reputation = domain_malicious or company_malicious
    boost = (25.0 if confirmed_verified else 0.0) + (28.0 if malicious_reputation else 0.0)
    score = int(round(_clamp(base_score + boost, 0.0, 100.0)))
    inconclusive = coverage < _LOW_COVERAGE_THRESHOLD or not available

    evidence_lines: list[str] = []
    for lines in (
        ml_evidence,
        message_evidence,
        *(rule_results[name][2] for name in SIGNAL_CATEGORIES),
        domain_evidence,
        company_evidence,
        history_evidence,
    ):
        for line in lines:
            if line not in evidence_lines:
                evidence_lines.append(line)
    if threat_checked and not rule_results["threat"][1]:
        evidence_lines.append(
            "The threat-indicator store was queried and no matching indicator was observed; "
            "absence of a match does not establish legitimacy."
        )
    if not evidence_lines:
        evidence_lines.append(
            "No usable model output, indicator or external intelligence was supplied; "
            "the score is not evidence of safety."
        )
    if inconclusive:
        missing = [name for name in SIGNAL_CATEGORIES if name not in available]
        evidence_lines.append(
            f"Evidence coverage is only {coverage:.0%}; unavailable signal categories: {', '.join(missing)}."
        )

    verified_fraction = 0.0
    supplied_indicators = [ind for ind in (indicators or []) if isinstance(ind, Mapping)]
    if supplied_indicators:
        verified_fraction = sum(
            1 for ind in supplied_indicators if _flag(ind.get("independently_verified"))
        ) / len(supplied_indicators)
    strongest = max(component_scores.values(), default=0.0)
    confidence = 0.12 + 0.45 * coverage + 0.35 * strongest + 0.08 * verified_fraction
    confidence = min(confidence, 0.42) if inconclusive else min(confidence, 0.95)
    confidence = _clamp(confidence)

    if inconclusive:
        summary = (
            "Assessment is inconclusive because the available evidence covers only "
            f"{coverage:.0%} of signal categories. This score must not be read as reassurance "
            "about the legitimacy of the offer."
        )
    elif score >= 80:
        summary = "Multiple strong or independently verified signals indicate critical offer-fraud risk."
    elif score >= 60:
        summary = "High risk: strong warning signals were observed and warrant immediate escalation."
    elif score >= 40:
        summary = "Moderate risk: meaningful warning signals were observed; independent verification is advised."
    elif score >= 20:
        summary = "Limited warning signals were observed; continue standard verification."
    else:
        summary = "Few risk signals were observed in the available evidence; monitoring is still recommended."

    assessment = RiskAssessment(
        score=score,
        category=_categorise(score, settings),
        inconclusive=bool(inconclusive),
        summary=summary,
        evidence_summary=evidence_lines,
        recommended_actions=_actions(score, inconclusive, evidence_lines, coverage),
        confidence=confidence,
        uncertainty=round(1.0 - confidence, 6),
        data_coverage=_clamp(coverage),
        weights_version=_weights_version(weights, bands),
        signal_weights={name: float(round(value, 6)) for name, value in weights.items()},
        unavailable_signals=[name for name in SIGNAL_CATEGORIES if name not in available],
        component_scores={name: float(round(value, 6)) for name, value in component_scores.items()},
    )
    return assessment.model_dump()


__all__ = [
    "CATEGORY_LABELS",
    "DEFAULT_BANDS",
    "DEFAULT_WEIGHTS",
    "SIGNAL_CATEGORIES",
    "_categorise",
    "score_risk",
]
