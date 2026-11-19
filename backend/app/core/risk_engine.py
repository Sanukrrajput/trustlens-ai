"""Explainable, verification-aware risk scoring.

Why thresholds and boosts are calibrated this way
-------------------------------------------------
The score is *not* a model confidence value. It is a weighted blend of six
independent evidence components whose weights come from ``settings.risk_weights``
and are renormalised over whichever sources are actually available. This means a
missing domain lookup cannot be mistaken for a "clean" domain.

Category bands are deliberately conservative:

* 0-19   Low observed risk       - only weak/neutral signals, or a very small
         amount of evidence. Never used to declare a sender safe.
* 20-39  Limited warning signals - one or two unverified anomalies.
* 40-59  Moderate risk           - needs at least one meaningful signal, such as
         a verified inconsistency or a strong text model result.
* 60-79  High risk               - requires corroboration or a confirmed malicious
         reputation signal.
* 80-100 Critical risk indicators - reserved for multiple independent strong
         signals (e.g. confirmed malicious indicator plus malicious domain).

Because a single component can only contribute its weight (at most 28% of the
total for ML), two explicit boosts encode the asymmetry between weak and strong
evidence: +25 points for an independently verified confirmed-malicious /
verified-inconsistency indicator, and +28 points for confirmed malicious domain
or company reputation. These boosts are applied to the *available-evidence*
score and capped at 100. They are large enough that verified signals dominate
unverified ones, but not so large that one signal alone reaches the critical band
without corroboration.

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

_COMPONENT_NAMES = ("ml", "rules", "domain", "company", "history", "message")

CATEGORY_BANDS: tuple[tuple[int, int, str], ...] = (
    (0, 19, "Low observed risk"),
    (20, 39, "Limited warning signals"),
    (40, 59, "Moderate risk"),
    (60, 79, "High risk"),
    (80, 100, "Critical risk indicators"),
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


def _categorise(score: int) -> str:
    for low, high, label in CATEGORY_BANDS:
        if low <= score <= high:
            return label
    return CATEGORY_BANDS[-1][2]


def _weights(settings: Any) -> dict[str, float]:
    raw = getattr(settings, "risk_weights", None)
    if not isinstance(raw, Mapping) or not raw:
        raw = {name: 1.0 / len(_COMPONENT_NAMES) for name in _COMPONENT_NAMES}
    cleaned = {name: max(0.0, _number(raw.get(name, 0.0))) for name in _COMPONENT_NAMES}
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
            f"ML model {name} reported fraud probability "
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
        return 0.0, 0.0, [], False
    score = _clamp((1.0 - math.exp(-positive / 0.65)) - supportive)
    ranked.sort(reverse=True)
    return score, 1.0, [text for _, text in ranked[:3]], confirmed_verified


def _domain_component(domain: dict[str, Any]) -> tuple[float, float, list[str], bool]:
    data = _as_dict(domain)
    if not data:
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

    if _flag(data.get("tls_valid")) is False and "tls_valid" in data:
        risk = _clamp(risk + 0.1)

    if _flag(data.get("verified")) or _flag(data.get("legitimate")):
        risk *= 0.4

    if not evidence:
        evidence.append("Domain intelligence was supplied but contained no recognised risk fields.")
    return _clamp(risk), 1.0, evidence[:3], malicious


def _company_component(company: dict[str, Any]) -> tuple[float, float, list[str], bool]:
    data = _as_dict(company)
    if not data:
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
    if not data:
        return 0.0, 0.0, []
    risk = 0.0
    evidence: list[str] = []
    if _flag(data.get("repeat_offender")) or _flag(data.get("known_scammer")):
        risk = max(risk, 0.95)
        evidence.append("Sender/employer is flagged as a repeat offender in historical records.")
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
        evidence.append("Historical intelligence was supplied but contained no recognised risk fields.")
    return _clamp(risk), 1.0, evidence[:3]


def _message_component(message: dict[str, Any]) -> tuple[float, float, list[str]]:
    data = _as_dict(message)
    if not data:
        return 0.0, 0.0, []
    risk = 0.0
    evidence: list[str] = []
    if _flag(data.get("payment_demand")):
        risk = max(risk, 0.85)
        evidence.append("Message demands a payment or fee from the candidate.")
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
        evidence.append("Sender domain does not match the claimed employer domain.")
    attachments = max(0.0, _number(data.get("attachment_count"), 0.0))
    if attachments > 0:
        risk = _clamp(risk + min(attachments, 3) * 0.08)
        evidence.append(f"Message contains {int(attachments)} attachment(s).")
    if not evidence:
        evidence.append("Message intelligence was supplied but contained no recognised risk fields.")
    return _clamp(risk), 1.0, evidence[:3]


def _weights_version(weights: dict[str, float]) -> str:
    payload = json.dumps(weights, sort_keys=True, separators=(",", ":"))
    return "w1-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _actions(score: int, inconclusive: bool, evidence: list[str], coverage: float) -> list[str]:
    actions: list[str] = []
    if inconclusive:
        actions.append(
            f"Treat this result as inconclusive: only {coverage:.0%} of signal sources were available. "
            "Collect missing evidence before making a decision."
        )
    joined = " ".join(evidence).lower()
    if score >= 60:
        actions.extend(
            [
                "Do not transfer money, buy gift cards, or share OTPs, CVV or bank details.",
                "Escalate to a human fraud reviewer and preserve the posting and message history.",
            ]
        )
    elif score >= 40:
        actions.extend(
            [
                "Verify the employer through the official corporate registry and a company-owned domain.",
                "Insist on a verifiable interview before sharing identity documents.",
            ]
        )
    else:
        actions.append("Continue standard verification and retain the listing and communications for the record.")
    if score >= 80:
        actions.append("Report the posting and sender to the job platform and the relevant authority.")
    if "payment" in joined or "fee" in joined:
        actions.append("Remember that legitimate employers do not charge candidates to secure a job.")
    if "sensitive" in joined or "bank" in joined:
        actions.append("Never provide full banking credentials or one-time passwords during recruitment.")
    # Preserve order while removing duplicates.
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
) -> dict:
    """Combine all available evidence into a :class:`RiskAssessment` dictionary.

    The returned dictionary validates against ``app.schemas.RiskAssessment`` and
    is therefore safe to pass straight to API serialisation.
    """
    weights = _weights(settings)
    ml_score, ml_coverage, ml_evidence = _ml_component(ml_predictions or [])
    rules_score, rules_coverage, rules_evidence, confirmed_verified = _rules_component(indicators or [])
    domain_score, domain_coverage, domain_evidence, domain_malicious = _domain_component(domain)
    company_score, company_coverage, company_evidence, company_malicious = _company_component(company)
    history_score, history_coverage, history_evidence = _historical_component(historical)
    message_score, message_coverage, message_evidence = _message_component(message)

    component_scores = {
        "ml": ml_score,
        "rules": rules_score,
        "domain": domain_score,
        "company": company_score,
        "history": history_score,
        "message": message_score,
    }
    coverage_by_component = {
        "ml": ml_coverage,
        "rules": rules_coverage,
        "domain": domain_coverage,
        "company": company_coverage,
        "history": history_coverage,
        "message": message_coverage,
    }

    available = [name for name in _COMPONENT_NAMES if coverage_by_component[name] > 0]
    weight_total = sum(weights[name] for name in available)
    if not available or weight_total <= 0:
        base_score = 0.0
        coverage = 0.0
    else:
        coverage = _clamp(sum(weights[name] for name in available))
        weighted = sum(weights[name] * component_scores[name] for name in available) / weight_total
        base_score = 100.0 * weighted

    malicious_reputation = domain_malicious or company_malicious
    boost = (25.0 if confirmed_verified else 0.0) + (28.0 if malicious_reputation else 0.0)
    score = int(round(_clamp(base_score + boost, 0.0, 100.0)))

    inconclusive = coverage < _LOW_COVERAGE_THRESHOLD or not available
    if inconclusive:
        score = int(round(_clamp(float(score), 0.0, 100.0)))

    evidence_lines: list[str] = []
    for lines in (ml_evidence, rules_evidence, domain_evidence, company_evidence, history_evidence, message_evidence):
        evidence_lines.extend(lines)
    if not evidence_lines:
        evidence_lines.append(
            "No usable ML predictions, indicators or external intelligence were supplied; "
            "the score is not evidence of safety."
        )
    if inconclusive:
        missing = [name for name in _COMPONENT_NAMES if name not in available]
        evidence_lines.append(
            f"Evidence coverage is only {coverage:.0%}; unavailable sources: {', '.join(missing)}."
        )

    verified_fraction = 0.0
    supplied_indicators = [ind for ind in (indicators or []) if isinstance(ind, Mapping)]
    if supplied_indicators:
        verified_fraction = sum(1 for ind in supplied_indicators if _flag(ind.get("independently_verified"))) / len(supplied_indicators)
    strongest = max(component_scores.values(), default=0.0)
    confidence = 0.12 + 0.45 * coverage + 0.35 * strongest + 0.08 * verified_fraction
    confidence = min(confidence, 0.42) if inconclusive else min(confidence, 0.95)

    if inconclusive:
        summary = (
            "Assessment is inconclusive because the available evidence covers only "
            f"{coverage:.0%} of signal sources. This score must not be read as reassurance "
            "about the legitimacy of the posting or sender."
        )
    elif score >= 80:
        summary = "Multiple strong or independently verified signals indicate critical recruitment-fraud risk."
    elif score >= 60:
        summary = "High risk: strong warning signals were observed and warrant immediate escalation."
    elif score >= 40:
        summary = "Moderate risk: meaningful warning signals were observed; independent verification is advised."
    elif score >= 20:
        summary = "Limited warning signals were observed; continue standard verification."
    else:
        summary = "Few risk signals were observed in the available evidence; monitoring is still recommended."

    actions = _actions(score, inconclusive, evidence_lines, coverage)

    assessment = RiskAssessment(
        score=score,
        category=_categorise(score),
        inconclusive=bool(inconclusive),
        summary=summary,
        evidence_summary=evidence_lines,
        recommended_actions=actions,
        confidence=_clamp(confidence),
        data_coverage=_clamp(coverage),
        weights_version=_weights_version(weights),
        component_scores={name: float(round(value, 6)) for name, value in component_scores.items()},
    )
    return assessment.model_dump()
