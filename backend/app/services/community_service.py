"""Community-report integrity, reputation and moderation helpers.

The community category is deliberately conservative. User reports are claims, not
proof, and a single report never changes an entity's risk classification. Only
moderator-reviewed reports from at least two distinct reporters can contribute a
decision-support indicator, and even then the indicator is marked unverified by
an independent external source.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from pymongo.errors import DuplicateKeyError

from app.core.security import utcnow
from app.db.repositories import Repositories
from app.intelligence import iso, make_indicator, registrable_domain

EVIDENCE_STATES = frozenset({"verified", "corroborated"})

MODERATION_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"pending", "verified", "corroborated", "false_report", "dismissed"}),
    "verified": frozenset({"verified", "corroborated", "false_report", "dismissed"}),
    "corroborated": frozenset({"corroborated", "false_report", "dismissed"}),
    "false_report": frozenset({"false_report", "pending"}),
    "dismissed": frozenset({"dismissed", "pending", "verified"}),
}

STATE_TO_STATUS: dict[str, str] = {
    "pending": "pending_review",
    "verified": "actioned",
    "corroborated": "actioned",
    "false_report": "dismissed",
    "dismissed": "dismissed",
}

STATE_AUDIT_ACTION: dict[str, str] = {
    "pending": "admin.report_reopened",
    "verified": "admin.report_verified",
    "corroborated": "admin.report_corroborated",
    "false_report": "admin.report_marked_false",
    "dismissed": "admin.report_dismissed",
}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalise_claim(value: str) -> str:
    """Normalise free text for duplicate grouping without altering stored text."""

    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:500]


def entity_key_for_analysis(extracted: dict[str, Any] | None, target_url: str = "") -> str:
    """Return a stable pseudonymous entity key, or '' when none can be derived."""

    data = dict(extracted or {})
    fingerprint = str(data.get("company_fingerprint") or "").strip()
    if fingerprint:
        return f"company:{fingerprint}"

    candidates = [target_url, *(data.get("urls") or [])]
    for candidate in candidates:
        domain = registrable_domain(candidate)
        if domain:
            return f"domain:{_sha256(domain)}"

    for email in data.get("recruiter_emails") or []:
        domain = registrable_domain(str(email).rsplit("@", 1)[-1])
        if domain:
            return f"email_domain:{_sha256(domain)}"
    return ""


def reputation_for_user(repos: Repositories, user_id: str) -> dict[str, Any]:
    """Compute a transparent, bounded reputation score from moderation outcomes.

    A new reporter starts at a neutral 0.5. The score is a weighting input only;
    it is never treated as proof that a claim is true or false.
    """

    basis = {
        "verified": 0,
        "corroborated": 0,
        "false_report": 0,
        "dismissed": 0,
        "pending": 0,
    }
    for report in repos.user_reports.for_user(str(user_id)):
        state = str(report.get("moderation_state") or "pending")
        if state in basis:
            basis[state] += 1

    score = (
        0.5
        + 0.10 * basis["verified"]
        + 0.15 * basis["corroborated"]
        - 0.30 * basis["false_report"]
        - 0.10 * basis["dismissed"]
    )
    return {
        "score": round(max(0.05, min(0.95, score)), 3),
        "basis": basis,
        "computed_at": utcnow(),
    }


def moderation_state_from_status(status: str) -> str:
    """Map the legacy review status onto the new state without over-claiming.

    A legacy ``reviewed`` status only means somebody looked at the report. It is
    deliberately *not* promoted to a verification state.
    """

    if status == "actioned":
        return "verified"
    if status == "dismissed":
        return "dismissed"
    return "pending"


def submit_report(
    *,
    repos: Repositories,
    analysis_doc: dict[str, Any],
    user_id: str,
    category: str,
    report_type: str,
    details: str,
    evidence_url: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """Insert a report or return the existing exact duplicate.

    The returned boolean is True only when an existing report was reused. Same
    user + same entity + same claim is a duplicate; a different user reporting
    the same claim is allowed because independent corroboration is the point.
    """

    actor = str(user_id)
    entity_key = entity_key_for_analysis(analysis_doc.get("extracted") or {})
    claim_key = _sha256(f"{category}|{report_type}|{normalise_claim(details)}")
    dedupe_key = _sha256(f"{actor}|{entity_key}|{claim_key}")
    duplicate_group_key = _sha256(f"{entity_key}|{claim_key}")

    existing = repos.user_reports.by_dedupe_key(dedupe_key)
    if existing:
        return _as_duplicate(existing, repos, duplicate_group_key), True

    document = {
        "analysis_id": str(analysis_doc.get("_id")),
        "user_id": actor,
        "category": category,
        "report_type": report_type,
        "details": details,
        "evidence_url": evidence_url or None,
        "status": "pending_review",
        "moderation_state": "pending",
        "entity_key": entity_key,
        "claim_key": claim_key,
        "dedupe_key": dedupe_key,
        "duplicate_group_key": duplicate_group_key,
        "duplicate_of": None,
        "duplicate_count": repos.user_reports.count({"duplicate_group_key": duplicate_group_key}),
        "reporter_reputation": reputation_for_user(repos, actor),
        "reviewed_by": None,
        "reviewed_at": None,
        "review_notes": None,
        "is_false_report": False,
        "false_report_reason": None,
        "created_at": utcnow(),
    }
    try:
        inserted = repos.user_reports.insert(document)
    except DuplicateKeyError:
        raced = repos.user_reports.by_dedupe_key(dedupe_key)
        if raced:
            return _as_duplicate(raced, repos, duplicate_group_key), True
        raise
    return inserted, False


def _as_duplicate(document: dict[str, Any], repos: Repositories, group_key: str) -> dict[str, Any]:
    result = dict(document)
    result["duplicate"] = True
    result["duplicate_count"] = repos.user_reports.count({"duplicate_group_key": group_key})
    return result


class CommunityIntelligence:
    """Turn moderated reports into an honest, corroboration-gated signal."""

    def __init__(self, repos: Repositories) -> None:
        self.repos = repos

    def assess(self, entity_key: str) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": "no_stable_entity",
            "entity_key": "",
            "supporting_reports": 0,
            "independent_reporters": 0,
            "average_reputation": 0.0,
            "weighted_support": 0.0,
            "indicators": [],
            "limitations": [
                "No stable company or domain fingerprint could be derived from this submission."
            ],
        }
        if not entity_key:
            return result

        result["entity_key"] = entity_key
        reports = self.repos.user_reports.for_entity(entity_key)
        eligible: list[dict[str, Any]] = []
        for report in reports:
            if report.get("category") != "community":
                continue
            if report.get("moderation_state") not in EVIDENCE_STATES:
                continue
            if report.get("is_false_report") or report.get("status") == "dismissed":
                continue
            eligible.append(report)

        by_reporter: dict[str, dict[str, Any]] = {}
        for report in eligible:
            reporter = str(report.get("user_id") or "")
            if not reporter:
                continue
            reputation = _reputation_score(report.get("reporter_reputation"))
            previous = by_reporter.get(reporter)
            if previous is None or reputation > _reputation_score(previous.get("reporter_reputation")):
                by_reporter[reporter] = report

        independent = len(by_reporter)
        result["supporting_reports"] = len(eligible)
        result["independent_reporters"] = independent
        result["limitations"] = [
            "Community reports are user claims, not proof of fraud.",
            "Moderator verification records a review decision, not independent external corroboration.",
            "A single report cannot create a community risk indicator.",
        ]
        if independent < 2:
            result["status"] = "insufficient_independent_reports"
            return result

        reputations = [_reputation_score(item.get("reporter_reputation")) for item in by_reporter.values()]
        average_reputation = round(sum(reputations) / independent, 3)
        weighted_support = round(sum(reputations), 3)
        extra_reporters = independent - 2
        severity = round(min(0.75, 0.35 + 0.10 * extra_reporters), 3)
        confidence = round(min(0.85, 0.35 + 0.25 * average_reputation), 3)
        weight = round(min(1.5, 0.8 + 0.15 * extra_reporters), 3)

        result.update(
            {
                "status": "corroborated",
                "average_reputation": average_reputation,
                "weighted_support": weighted_support,
                "moderation_states": sorted({str(item.get("moderation_state")) for item in by_reporter.values()}),
                "indicators": [
                    make_indicator(
                        name="community_independently_corroborated",
                        status="suspicious",
                        severity=severity,
                        description=(
                            f"{independent} independent reporter(s) submitted moderator-reviewed claims about this "
                            f"entity (mean reporter reputation {average_reputation:.3f}). This is decision support "
                            "only and is not proof of fraud."
                        ),
                        source="community reports",
                        observed_at=iso(),
                        confidence=confidence,
                        independently_verified=False,
                        weight=weight,
                        signal_category="community",
                    )
                ],
            }
        )
        return result


def _reputation_score(value: Any) -> float:
    if isinstance(value, dict):
        value = value.get("score")
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, score))


def apply_moderation(
    *,
    repos: Repositories,
    report_id: str,
    admin_id: str,
    status: str | None,
    moderation_state: str | None,
    review_notes: str | None,
    false_report_reason: str | None,
) -> tuple[str, dict[str, Any] | None, str, str]:
    """Apply a moderator decision.

    Returns ``(outcome, document, previous_state, new_state)`` where outcome is
    one of ``ok``, ``not_found``, ``invalid_transition`` or ``reason_required``.
    """

    report = repos.user_reports.get(report_id)
    if not report:
        return "not_found", None, "", ""

    previous = str(report.get("moderation_state") or "pending")
    new_state = moderation_state or moderation_state_from_status(status or "")
    if new_state not in MODERATION_TRANSITIONS.get(previous, frozenset()):
        return "invalid_transition", report, previous, new_state
    if new_state == "false_report" and not (false_report_reason or "").strip():
        return "reason_required", report, previous, new_state

    effective_status = status or STATE_TO_STATUS[new_state]
    updated = repos.user_reports.update(
        report_id,
        {
            "status": effective_status,
            "moderation_state": new_state,
            "review_notes": review_notes or None,
            "reviewed_by": str(admin_id),
            "reviewed_at": utcnow(),
            "is_false_report": new_state == "false_report",
            "false_report_reason": false_report_reason.strip() if new_state == "false_report" and false_report_reason else None,
        },
    )
    return "ok", updated, previous, new_state


__all__ = [
    "EVIDENCE_STATES",
    "STATE_AUDIT_ACTION",
    "CommunityIntelligence",
    "apply_moderation",
    "entity_key_for_analysis",
    "moderation_state_from_status",
    "normalise_claim",
    "reputation_for_user",
    "submit_report",
]
