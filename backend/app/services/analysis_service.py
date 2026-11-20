"""End-to-end investigation orchestration.

Every analysis combines extraction, ML predictions, external intelligence (only
with explicit consent), explainable rules, anomaly checks and an evidence-based
risk assessment. All results are persisted in MongoDB.
"""

from __future__ import annotations

import hashlib
import io
import logging
import math
import re
import uuid
from typing import Any

from app.core.config import Settings
from app.core.security import contact_fingerprint, utcnow
from app.db.repositories import Repositories
from app.services.notification_service import NotificationService
from app.services.plan_service import PlanService
from app.utils.serialization import doc_out, json_safe

logger = logging.getLogger(__name__)


class DocumentParser:
    """Extract text from supported uploads without executing file content.

    Image text goes through the optional OCR engine, which reports
    ``not_configured`` instead of pretending that an image was read when no local
    OCR backend is installed.
    """

    SUPPORTED = {"application/pdf", "image/png", "image/jpeg", "image/webp", "text/plain"}

    @staticmethod
    def parse(filename: str, content: bytes, mime: str) -> tuple[str, dict[str, Any], list[str]]:
        limitations: list[str] = []
        image_result: dict[str, Any] = {}
        text = ""
        if mime == "application/pdf":
            try:
                import pdfplumber

                with pdfplumber.open(io.BytesIO(content)) as pdf:
                    pages = [(page.extract_text() or "") for page in pdf.pages[:20]]
                    text = "\n".join(pages)
                if len(text.strip()) < 20:
                    limitations.append("PDF contained little or no extractable text; it may be image-only.")
            except Exception as exc:  # noqa: BLE001
                limitations.append(f"PDF text extraction failed: {type(exc).__name__}")
        elif mime == "text/plain":
            text = content.decode("utf-8", errors="replace")[:200_000]
        elif mime.startswith("image/"):
            from app.intelligence.image.ocr import ImageOCR

            image_result = ImageOCR().extract(content, mime)
            text = str(image_result.get("text") or "")
            limitations.extend(str(item) for item in image_result.get("limitations") or [])
        else:
            limitations.append(f"Unsupported document type: {mime}")
        return text[:200_000], image_result, limitations


def _preview(text: str, limit: int = 280) -> str:
    redacted = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[email]", text or "")
    redacted = re.sub(r"(?:\+?91[\s-]?)?[6-9]\d{9}", "[phone]", redacted)
    redacted = re.sub(r"https?://\S+", "[url]", redacted)
    redacted = re.sub(r"\s+", " ", redacted).strip()
    return redacted[:limit]


def _number(value: Any, default: float = 0.0) -> float:
    """Read a numeric value from a raw number or a provenance-wrapped fact.

    Intelligence modules wrap observations as ``{"value": ..., "source": ...}``.
    Scoring code must accept that shape without treating the wrapper as a number.
    """
    if isinstance(value, dict):
        value = value.get("value")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _build_evidence_sources(
    *,
    attempted: list[str],
    succeeded: list[str],
    started_at: Any,
    sections: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Turn attempt bookkeeping into honest, timestamped source records.

    ``started_at`` is the analysis creation time: every listed source was
    attempted during this run. A source-specific ``observed_at`` is used when
    the engine supplied one. No source is upgraded to "succeeded" merely
    because it was attempted.
    """
    succeeded_set = set(succeeded)
    records: list[dict[str, Any]] = []
    for name in dict.fromkeys(attempted):
        section = sections.get(name) or {}
        raw_status = str(
            section.get("status")
            or section.get("verification_status")
            or section.get("state")
            or "attempted"
        )
        observed_at = section.get("observed_at") or started_at
        records.append(
            {
                "name": name,
                "status": "succeeded" if name in succeeded_set else raw_status,
                "attempted_at": started_at,
                "observed_at": observed_at,
                "detail": f"engine status: {raw_status}" if raw_status != "attempted" else None,
            }
        )
    return records


class AnalysisService:
    def __init__(
        self,
        settings: Settings,
        repos: Repositories,
        notifications: NotificationService,
        plans: PlanService,
    ) -> None:
        self.settings = settings
        self.repos = repos
        self.notifications = notifications
        self.plans = plans
        self._predictor = None
        self._domain = None
        self._company = None
        self._message = None
        self._anomaly = None
        self._brand = None
        self._threat = None

    def _services(self):
        if self._predictor is None:
            from app.ml.inference.predictor import TextPredictor

            self._predictor = TextPredictor(self.settings.model_dir)
        if self._domain is None:
            from app.intelligence.domain_analysis.analyser import DomainAnalyser

            self._domain = DomainAnalyser(self.settings, self.repos)
        if self._company is None:
            from app.intelligence.company_verification.verifier import CompanyVerifier

            self._company = CompanyVerifier(self.settings, self.repos)
        if self._message is None:
            from app.intelligence.message_analysis.analyser import MessageAnalyser

            self._message = MessageAnalyser()
        if self._anomaly is None:
            from app.intelligence.anomaly import AnomalyEngine

            self._anomaly = AnomalyEngine(self.settings, self.repos)
        if self._brand is None:
            from app.intelligence.brand_verification import BrandVerifier

            self._brand = BrandVerifier()
        if self._threat is None:
            from app.intelligence.threat_indicators import ThreatIndicatorStore

            self._threat = ThreatIndicatorStore(self.settings, self.repos)
        return self._predictor, self._domain, self._company, self._message, self._anomaly

    def run(self, user_id: str, analysis_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        allowed, reason = self.plans.can_scan(user_id)
        if not allowed:
            raise PermissionError(reason)

        client_request_id = payload.get("client_request_id")
        if client_request_id:
            existing = self.repos.analyses.find_idempotent(user_id, client_request_id)
            if existing:
                return doc_out(existing) or {}
        # Each stored analysis needs a distinct idempotency key, including when the
        # caller did not supply one (unique sparse indexes behave inconsistently
        # across MongoDB test doubles when the field is simply absent).
        storage_request_id = str(client_request_id or f"auto-{uuid.uuid4().hex}")

        consent = bool(payload.get("consent_external_lookups"))
        text = str(payload.get("text") or payload.get("description") or "")
        limitations: list[str] = list(payload.get("limitations") or [])
        sources_attempted: list[str] = []
        sources_succeeded: list[str] = []

        image_result: dict[str, Any] = {}
        if analysis_type == "document":
            text, image_result, doc_limitations = DocumentParser.parse(
                str(payload.get("filename", "upload")),
                bytes(payload.get("content", b"")),
                str(payload.get("mime", "text/plain")),
            )
            limitations.extend(doc_limitations)
            if image_result:
                sources_attempted.append("image_ocr")
                if image_result.get("status") == "ok":
                    sources_succeeded.append("image_ocr")

        record = self.repos.analyses.insert(
            {
                "user_id": user_id,
                "analysis_type": analysis_type,
                "status": "pending",
                # The MongoDB fraud_analyses validator requires a risk object even
                # for in-progress records. This placeholder is replaced with the
                # real assessment once scoring completes.
                "risk": {"score": 0, "category": "pending", "inconclusive": True},
                "created_at": utcnow(),
                "input_preview": _preview(text or payload.get("url", "")),
                "input_sha256": hashlib.sha256((text or str(payload.get("url", ""))).encode()).hexdigest(),
                "client_request_id": storage_request_id,
            }
        )
        analysis_id = str(record["_id"])

        try:
            from app.intelligence.extraction import extract_entities
            from app.intelligence.offer_rules import build_offer_indicators
            from app.intelligence.rules import build_rule_indicators
            from app.core.risk_engine import score_risk
            from app.services.community_service import CommunityIntelligence, entity_key_for_analysis

            predictor, domain_service, company_service, message_service, anomaly_engine = self._services()

            extracted = extract_entities(text)
            company_name = payload.get("company_name") or (extracted.get("company_names") or [None])[0]
            if company_name and not extracted.get("company_fingerprint"):
                extracted["company_fingerprint"] = contact_fingerprint(str(company_name))
            extracted["company_fingerprint"] = extracted.get("company_fingerprint") or ""

            offer_category = str(payload.get("offer_category") or "other")
            model_predictions: list[dict[str, Any]] = []
            if analysis_type == "offer":
                # No general-offer artifact is approved; use the honest rule fallback
                # instead of presenting a recruitment-text model as a general model.
                model_predictions.append(predictor.predict_offer(text, offer_category))
            if analysis_type in {"job", "document", "monitoring"}:
                model_predictions.append(predictor.predict_job(text))
            if analysis_type in {"message", "job", "document"}:
                model_predictions.append(predictor.predict_message(text, str(payload.get("channel", "unknown"))))

            message_result: dict[str, Any] = {}
            if analysis_type in {"message", "job", "document", "offer"}:
                message_result = message_service.analyse(
                    text,
                    str(payload.get("channel", "unknown")),
                    payload.get("sender") or payload.get("recruiter_email"),
                )
                sources_attempted.append("message_rules")
                sources_succeeded.append("message_rules")

            domain_result: dict[str, Any] = {}
            url_result: dict[str, Any] = {}
            target_url = str(
                payload.get("url")
                or payload.get("source_url")
                or (extracted.get("urls") or [None])[0]
                or ""
            )
            if target_url:
                sources_attempted.append("url_structure")
                if consent:
                    from app.intelligence.url_scanning.safe_fetch import SafeURLFetcher

                    url_result = SafeURLFetcher(self.settings).fetch(target_url)
                    sources_attempted.append("safe_url_fetch")
                    if url_result.get("status") not in {"error", "blocked"}:
                        sources_succeeded.append("safe_url_fetch")
                    target_url = str(url_result.get("final_url") or target_url)
                    domain_result = domain_service.analyse(target_url, refresh=False)
                    sources_attempted.extend(["rdap", "dns", "tls"])
                    for key in ("rdap", "dns", "tls"):
                        section = domain_result.get(key, {})
                        if isinstance(section, dict) and section.get("status") in {"ok", "available", "matched", "configured"}:
                            sources_succeeded.append(key)
                else:
                    limitations.append("External URL/domain lookups were not performed because consent was not provided.")
                    domain_result = {"status": "not_attempted", "reason": "external lookup consent not provided"}
            else:
                domain_result = {"status": "not_attempted", "reason": "no URL or domain found in submission"}

            company_result: dict[str, Any] = {}
            if company_name:
                sources_attempted.append("company_heuristics")
                if consent:
                    company_result = company_service.verify(
                        str(company_name),
                        website_url=target_url or None,
                        corporate_id=payload.get("corporate_id"),
                        consent_external=True,
                        consent_registry=bool(payload.get("consent_registry")),
                    )
                    sources_attempted.append("company_verification")
                    if company_result.get("verification_status") not in {None, "not_attempted"}:
                        sources_succeeded.append("company_verification")
                else:
                    company_result = {"verification_status": "not_attempted", "reason": "external lookup consent not provided"}
            else:
                company_result = {"verification_status": "not_attempted", "reason": "no company name identified"}

            anomaly_result = anomaly_engine.assess(
                {
                    "analysis_id": analysis_id,
                    "user_id": user_id,
                    "company_fingerprint": extracted.get("company_fingerprint"),
                    "emails": extracted.get("recruiter_emails", []),
                    "urls": extracted.get("urls", []),
                    "text": text,
                }
            )
            sources_attempted.append("historical_patterns")
            if anomaly_result.get("status") != "unavailable":
                sources_succeeded.append("historical_patterns")

            entity_key = entity_key_for_analysis(extracted, target_url)
            community_result = CommunityIntelligence(self.repos).assess(entity_key)
            sources_attempted.append("community_reports")
            if community_result.get("status") in {"corroborated", "insufficient_independent_reports", "no_stable_entity"}:
                sources_succeeded.append("community_reports")

            threat_values = [
                value
                for value in [
                    company_name,
                    extracted.get("company_fingerprint"),
                    target_url,
                    *list(extracted.get("urls") or []),
                    *list(extracted.get("recruiter_emails") or []),
                    *list(extracted.get("phone_numbers") or []),
                ]
                if value
            ]
            threat_result = self._threat.match(threat_values, analysis_type=analysis_type)
            sources_attempted.append("threat_indicator_store")
            # A local-store query that legitimately finds no match still succeeded.
            # "not_configured" refers to external feeds, not to a failed query.
            if threat_result.get("status") in {"ok", "no_match", "not_configured"}:
                sources_succeeded.append("threat_indicator_store")

            campaign = (
                {
                    "campaign_id": payload.get("campaign_id"),
                    "source_url": target_url or None,
                    "channel": payload.get("channel"),
                    "text_preview": _preview(text, 200),
                }
                if analysis_type in {"offer", "job", "document", "message", "url"}
                else {}
            )
            brand_result = self._brand.verify(
                claimed_brand=str(company_name or ""),
                campaign=campaign,
                company_result=company_result,
                domain_result=domain_result,
                threat_matches=list(threat_result.get("matches") or []),
                # Only engine-produced evidence is accepted here. User-supplied
                # screenshots or advert text are never treated as independent.
                campaign_evidence=[],
                consent_external_lookups=consent,
            )
            sources_attempted.append("brand_verification")
            if brand_result.get("status") == "ok":
                sources_succeeded.append("brand_verification")

            offer_indicators: list[dict[str, Any]] = []
            if analysis_type == "offer":
                sources_attempted.append("offer_rules")
                sources_succeeded.append("offer_rules")
                offer_indicators = build_offer_indicators(text, offer_category)

            # build_rule_indicators canonicalises and merges duplicate signals
            # across every engine, so the same observation is never counted twice.
            indicators = build_rule_indicators(
                extracted=extracted,
                domain=domain_result,
                company=company_result,
                message=message_result,
                historical=anomaly_result,
                image=image_result,
                brand=brand_result,
                threat=threat_result,
                offer={"indicators": offer_indicators},
                community=community_result,
            )

            for indicator in indicators:
                self.repos.risk_indicators.insert({**indicator, "analysis_id": analysis_id})

            domain_signals = domain_result.get("signals")
            domain_signals = domain_signals if isinstance(domain_signals, dict) else {}
            anomaly_signals = anomaly_result.get("signals")
            anomaly_signals = anomaly_signals if isinstance(anomaly_signals, dict) else {}
            anomaly_features = {
                "fee_mentions": len(extracted.get("payment_demands", [])),
                "sensitive_requests": len(extracted.get("sensitive_data_requests", [])),
                "personal_email": 1 if any("@" in email and not any(domain in email for domain in ["company", "corp"]) for email in extracted.get("recruiter_emails", [])) else 0,
                "domain_age_days": _number(domain_signals.get("domain_age_days"), 3650.0),
                "repeated_contacts": _number(anomaly_signals.get("repeated_contact_count"), 0.0),
                "company_mismatch": 1 if company_result.get("contradictions") else 0,
            }
            try:
                model_predictions.append(predictor.predict_anomaly(anomaly_features))
            except Exception as exc:  # noqa: BLE001
                limitations.append(f"Anomaly model unavailable: {type(exc).__name__}")

            risk = score_risk(
                ml_predictions=model_predictions,
                indicators=indicators,
                domain=domain_result,
                company=company_result,
                historical=anomaly_result,
                message=message_result,
                settings=self.settings,
                image=image_result,
                brand=brand_result,
                threat=threat_result,
            )

            missing_evidence = [
                "Official company registry evidence was not available."
                if company_result.get("verification_status") != "verified_with_evidence"
                else "",
                "Independent domain reputation was unavailable."
                if not any(key in domain_result for key in ("virustotal", "safe_browsing", "web_risk"))
                else "",
                (
                    "No verified sender identity was provided."
                    if analysis_type in {"offer", "message"}
                    else "No verified recruiter identity was provided."
                ),
            ]
            if analysis_type == "offer":
                missing_evidence.append(
                    "No independent evidence confirms that a named company authorised or published this specific offer."
                )
            if image_result and image_result.get("status") != "ok":
                missing_evidence.append("No text could be extracted from the submitted image; visual content was not verified.")
            missing_evidence.extend(brand_result.get("missing_evidence") or [])
            if community_result.get("status") in {"insufficient_independent_reports", "no_stable_entity"}:
                missing_evidence.append(
                    "Community intelligence did not provide independently corroborated reports for this entity."
                )
            if threat_result.get("status") == "not_configured":
                missing_evidence.append("No external threat feed was configured; only the local indicator store was checked.")
            missing_evidence = list(dict.fromkeys(item for item in missing_evidence if item))

            completed_at = utcnow()
            evidence_sources = _build_evidence_sources(
                attempted=sources_attempted,
                succeeded=sources_succeeded,
                started_at=record["created_at"],
                sections={
                    "image_ocr": image_result,
                    "message_rules": message_result,
                    "safe_url_fetch": url_result,
                    "rdap": domain_result.get("rdap") or {},
                    "dns": domain_result.get("dns") or {},
                    "tls": domain_result.get("tls") or {},
                    "company_heuristics": company_result,
                    "company_verification": company_result,
                    "historical_patterns": anomaly_result,
                    "community_reports": community_result,
                    "threat_indicator_store": threat_result,
                    "brand_verification": brand_result,
                },
            )

            result = {
                "id": analysis_id,
                "analysis_type": analysis_type,
                "offer_category": offer_category if analysis_type == "offer" else None,
                "status": "completed",
                "user_id": user_id,
                "created_at": record["created_at"],
                "completed_at": completed_at,
                "input_preview": record["input_preview"],
                "extracted": extracted,
                "model_predictions": model_predictions,
                "domain_intelligence": json_safe(domain_result) or {},
                "company_intelligence": json_safe(company_result) or {},
                "message_intelligence": json_safe(message_result) or {},
                "historical_intelligence": json_safe(anomaly_result) or {},
                "image_intelligence": json_safe(image_result) or {},
                "brand_intelligence": json_safe(brand_result) or {},
                "threat_intelligence": json_safe(threat_result) or {},
                "community_intelligence": json_safe(community_result) or {},
                "indicators": json_safe(indicators) or [],
                "evidence_sources": json_safe(evidence_sources) or [],
                "evidence_collected_at": completed_at,
                "missing_evidence": missing_evidence,
                "technical_limitations": (
                    limitations
                    + list(domain_result.get("limitations", []))
                    + list(company_result.get("limitations", []))
                    + list(brand_result.get("limitations", []))
                    + list(threat_result.get("limitations", []))
                ),
                "risk": risk,
                "sources_attempted": sources_attempted,
                "sources_succeeded": sources_succeeded,
                "url_intelligence": json_safe(url_result) or {},
            }
            self.repos.analyses.update(analysis_id, result)
            self.plans.consume_scan(user_id)

            user = self.repos.users.get(user_id)
            if risk.get("score", 0) >= 60 and user:
                self.notifications.high_risk_notification(
                    user_id, str(user.get("email") or ""), analysis_id, int(risk["score"])
                )
            logger.info("analysis completed id=%s type=%s score=%s", analysis_id, analysis_type, risk.get("score"))
            return result
        except Exception as exc:
            logger.exception("analysis failed id=%s", analysis_id)
            self.repos.analyses.update(
                analysis_id,
                {
                    "status": "failed",
                    "error": str(exc),
                    "completed_at": utcnow(),
                },
            )
            raise
