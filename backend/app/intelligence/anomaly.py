"""Historical/repeated-pattern intelligence.

Counts come from MongoDB when repositories are supplied. Repetition and shared
infrastructure are explicitly weak signals and are never treated as proof of
fraud. An optional registered ML model may contribute a prediction, but its
absence is reported honestly.
"""

from __future__ import annotations

import importlib
import re
from typing import Any

from app.intelligence import (
    company_fingerprint,
    dedupe,
    email_fingerprint,
    extract_host,
    iso,
    make_indicator,
    normalise_email,
    registrable_domain,
)


class AnomalyEngine:
    """Aggregate repeated patterns across stored analyses and job listings."""

    def __init__(self, settings: Any, repos: Any = None) -> None:
        self.settings = settings
        self.repos = repos

    @staticmethod
    def _safe_count(repo: Any, query: dict[str, Any]) -> int | None:
        if repo is None:
            return None
        try:
            return int(repo.count(query))
        except Exception:
            return None

    @staticmethod
    def _safe_users(repo: Any, query: dict[str, Any]) -> int | None:
        if repo is None:
            return None
        try:
            docs = repo.find(query, projection={"user_id": 1}, limit=500) or []
            return len({str(doc.get("user_id")) for doc in docs if isinstance(doc, dict) and doc.get("user_id")})
        except Exception:
            return None

    @staticmethod
    def _regex(phrase: str) -> dict[str, str]:
        return {"$regex": re.escape(str(phrase)), "$options": "i"}

    def _blacklist_hits(self, fingerprints: list[str]) -> int:
        repo = getattr(self.repos, "blacklist", None) if self.repos is not None else None
        if repo is None or not fingerprints:
            return 0
        hits = 0
        for fingerprint in fingerprints:
            try:
                if repo.find_one({"$or": [{"token": fingerprint}, {"value": fingerprint}, {"fingerprint": fingerprint}]}):
                    hits += 1
            except Exception:
                return 0
        return hits

    def _model(self, features: dict[str, Any]) -> dict[str, Any]:
        repos = self.repos
        registered = None
        if repos is not None:
            models = getattr(repos, "models", None)
            if models is not None:
                try:
                    registered = models.active("anomaly")
                except Exception:
                    registered = None
        if not registered:
            return {
                "status": "not_available",
                "prediction": None,
                "limitations": ["No active anomaly model is registered; no ML prediction was fabricated."],
                "observed_at": iso(),
            }
        try:
            module = importlib.import_module("app.ml.inference")
            predictor = getattr(module, "predict_anomaly", None) or getattr(module, "predict", None)
            if not callable(predictor):
                raise AttributeError("no callable anomaly predictor in app.ml.inference")
            try:
                prediction = predictor(features)
            except TypeError:
                prediction = predictor([features])
            return {"status": "ok", "prediction": prediction, "limitations": [], "observed_at": iso()}
        except Exception as exc:
            return {
                "status": "not_available",
                "prediction": None,
                "limitations": [f"Registered anomaly model could not be executed: {type(exc).__name__}: {exc}"],
                "observed_at": iso(),
            }

    def assess(self, context: dict[str, Any]) -> dict[str, Any]:
        """Assess repeated patterns for the supplied analysis context."""
        context = context or {}
        limitations: list[str] = []
        extracted = context.get("extracted") if isinstance(context.get("extracted"), dict) else {}

        email = normalise_email(
            context.get("recruiter_email")
            or (extracted.get("recruiter_emails") or [None])[0]
            or context.get("sender")
        )
        recruiter_fp = email_fingerprint(email) or str(context.get("recruiter_fingerprint") or "")
        domains = dedupe(
            list(context.get("domains") or [])
            + list(extracted.get("domain_candidates") or [])
            + ([registrable_domain(extract_host(context.get("domain")))] if context.get("domain") else [])
        )
        payment_phrases = dedupe(
            list(context.get("payment_phrases") or []) + list(extracted.get("payment_demands") or [])
        )[:5]
        company_names = dedupe(
            list(context.get("company_names") or []) + list(extracted.get("company_names") or [])
        )
        company_fp = str(
            context.get("company_fingerprint")
            or extracted.get("company_fingerprint")
            or (company_fingerprint(company_names[0]) if company_names else "")
        )

        analyses = getattr(self.repos, "analyses", None) if self.repos is not None else None
        listings = getattr(self.repos, "job_listings", None) if self.repos is not None else None
        if analyses is None:
            limitations.append("No analyses repository was supplied; historical analysis counts are unavailable.")
        if listings is None:
            limitations.append("No job-listings repository was supplied; historical listing counts are unavailable.")

        queries: dict[str, dict[str, Any]] = {}
        if recruiter_fp or email:
            queries["recruiter"] = {
                "$or": [
                    {"extracted.recruiter_fingerprint": recruiter_fp},
                    {"recruiter_fingerprint": recruiter_fp},
                    {"extracted.recruiter_emails": email},
                    {"recruiter_email": email},
                ]
            }
        if domains:
            queries["domain"] = {
                "$or": [
                    {"extracted.domain_candidates": {"$in": domains}},
                    {"domain_intelligence.domain": {"$in": domains}},
                    {"domain": {"$in": domains}},
                ]
            }
        if payment_phrases:
            clauses: list[dict[str, Any]] = []
            for phrase in payment_phrases:
                pattern = self._regex(phrase)
                clauses.extend(
                    [
                        {"extracted.payment_demands": pattern},
                        {"payment_phrase": pattern},
                        {"message_intelligence.signals.fee_demand.matches": pattern},
                    ]
                )
            queries["payment_phrase"] = {"$or": clauses}
        if company_names or company_fp:
            queries["company"] = {
                "$or": [
                    {"extracted.company_fingerprint": company_fp},
                    {"company_fingerprint": company_fp},
                    {"extracted.company_names": {"$in": company_names}},
                    {"company_name": {"$in": company_names}},
                ]
            }

        historical_counts: dict[str, Any] = {}
        for key, query in queries.items():
            analysis_count = self._safe_count(analyses, query)
            listing_count = self._safe_count(listings, query)
            if analysis_count is None and listing_count is None:
                historical_counts[key] = {"analyses": 0, "listings": 0, "available": False}
                continue
            historical_counts[key] = {
                "analyses": analysis_count or 0,
                "listings": listing_count or 0,
                "distinct_users": self._safe_users(analyses, query),
                "available": True,
            }
        for key in ("recruiter", "domain", "payment_phrase", "company"):
            historical_counts.setdefault(
                key, {"analyses": 0, "listings": 0, "available": self.repos is not None}
            )

        blacklist_hits = self._blacklist_hits([value for value in [recruiter_fp, company_fp] if value])
        historical_counts["blacklist_hits"] = blacklist_hits

        signals: dict[str, Any] = {}
        indicators: list[dict[str, Any]] = []
        descriptions = {
            "recruiter": "The same recruiter contact or fingerprint was seen in previous records.",
            "domain": "The same domain was seen in previous records.",
            "payment_phrase": "Similar payment language was seen in previous records.",
            "company": "The same company name or fingerprint was seen in previous records.",
        }
        for key, description in descriptions.items():
            entry = historical_counts.get(key) or {}
            total = int(entry.get("analyses", 0) or 0) + int(entry.get("listings", 0) or 0)
            detected = total > 1
            signals[key] = {
                "detected": detected,
                "count": total,
                "available": bool(entry.get("available")),
                "confidence": min(0.75, 0.3 + 0.1 * total) if detected and entry.get("available") else 0.0,
                "explanation": description + " Repetition is not proof of fraud.",
            }
            if detected:
                indicators.append(
                    make_indicator(
                        name=f"historical_repeated_{key}",
                        status="suspicious",
                        severity=min(0.6, 0.25 + 0.05 * total),
                        description=f"{description} Seen {total} time(s) in stored records.",
                        source="MongoDB analyses/job_listings",
                        confidence=signals[key]["confidence"],
                    )
                )

        repeated_only_domain = signals["domain"]["detected"] and not any(
            signals[other]["detected"] for other in ("recruiter", "payment_phrase", "company")
        )
        signals["shared_infrastructure_only"] = {
            "detected": bool(repeated_only_domain or context.get("shared_infrastructure")),
            "confidence": 0.2,
            "explanation": "Shared domains, hosting or mail providers are common and are explicitly not evidence of fraud.",
        }
        if signals["shared_infrastructure_only"]["detected"]:
            indicators.append(
                make_indicator(
                    name="shared_infrastructure_not_proof",
                    status="supportive",
                    severity=0.0,
                    description="Only shared infrastructure/repeated domain was observed; this is not treated as evidence of fraud.",
                    source="historical heuristic",
                    confidence=0.4,
                    weight=0.2,
                )
            )

        if blacklist_hits:
            indicators.append(
                make_indicator(
                    name="blacklist_match",
                    status="confirmed_malicious",
                    severity=0.9,
                    description=f"A supplied fingerprint matched {blacklist_hits} stored blacklist record(s).",
                    source="MongoDB blacklist",
                    confidence=0.85,
                )
            )
            signals["blacklist"] = {"detected": True, "count": blacklist_hits, "confidence": 0.85}
        else:
            signals["blacklist"] = {"detected": False, "count": 0, "confidence": 0.0}

        features = {
            "counts": historical_counts,
            "signals": {key: value.get("detected") for key, value in signals.items() if isinstance(value, dict)},
        }
        model = self._model(features)
        if model.get("status") != "ok":
            limitations.extend(model.get("limitations") or [])
        limitations.append("Historical absence of a pattern does not establish legitimacy.")

        return {
            "status": "ok" if self.repos is not None else "limited",
            "observed_at": iso(),
            "historical_counts": historical_counts,
            "signals": signals,
            "indicators": indicators,
            "model": model,
            "limitations": limitations,
        }


__all__ = ["AnomalyEngine"]
