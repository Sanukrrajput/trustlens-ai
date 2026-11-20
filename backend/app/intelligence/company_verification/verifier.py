"""Company corroboration with explicit consent gates.

A company is never declared verified on the strength of a single weak signal.
Registry confirmation requires a configured, licensed provider; otherwise the
result is partial/unverified and says exactly what is missing.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Any

import requests

from app.intelligence import (
    PERSONAL_EMAIL_DOMAINS,
    company_fingerprint,
    dedupe,
    fact,
    iso,
    make_indicator,
    normalise_company_name,
    registrable_domain,
    setting,
)
from app.intelligence.domain_analysis import DomainAnalyser
from app.intelligence.url_scanning.safe_fetch import SafeURLFetcher

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
TOKEN_STOPWORDS = {"the", "and", "of", "for", "group", "india", "limited", "pvt", "private", "company", "co"}
REGISTRY_INACTIVE = {"inactive", "struck off", "struck-off", "deregistered", "dissolved", "removed"}


def _visible_text(markup: str) -> str:
    cleaned = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1\s*>", " ", markup or "")
    cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
    return re.sub(r"\s+", " ", html.unescape(cleaned)).strip()


def _meta_description(markup: str) -> str:
    match = re.search(
        r"<meta\b[^>]*\bname\s*=\s*[\"']description[\"'][^>]*\bcontent\s*=\s*[\"']([^\"']*)[\"']",
        markup or "",
        re.I,
    ) or re.search(
        r"<meta\b[^>]*\bcontent\s*=\s*[\"']([^\"']*)[\"'][^>]*\bname\s*=\s*[\"']description[\"']",
        markup or "",
        re.I,
    )
    return html.unescape(match.group(1)) if match else ""


def _company_tokens(name: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", normalise_company_name(name))
        if len(token) >= 2 and token not in TOKEN_STOPWORDS
    ]


class CompanyVerifier:
    """Corroborate a company name using consented, evidence-bearing sources."""

    def __init__(self, settings: Any, repos: Any = None) -> None:
        self.settings = settings
        self.repos = repos
        self.timeout = max(0.5, float(setting(settings, "fetch_timeout_seconds", 8.0)))
        self.fetcher = SafeURLFetcher(settings)
        self.domain_analyser = DomainAnalyser(settings, repos)

    def _cached(self, fingerprint: str) -> dict[str, Any] | None:
        repo = getattr(self.repos, "companies", None) if self.repos is not None else None
        if repo is None or not fingerprint:
            return None
        try:
            cached = repo.by_fingerprint(fingerprint)
        except Exception:
            return None
        if not cached:
            return None
        updated = cached.get("updated_at")
        if isinstance(updated, datetime):
            age_hours = (datetime.now(timezone.utc) - (updated if updated.tzinfo else updated.replace(tzinfo=timezone.utc))).total_seconds() / 3600
            if age_hours > float(setting(self.settings, "domain_refresh_interval_hours", 24)):
                return None
        return {key: value for key, value in cached.items() if key not in {"_id", "name_fingerprint"}}

    @staticmethod
    def _registry_value(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for key in keys:
            value = payload.get(key)
            if value not in (None, "", []):
                return value
        return None

    def _registry(
        self,
        company_name: str,
        corporate_id: str | None,
        consent_registry: bool,
    ) -> dict[str, Any]:
        url = str(setting(self.settings, "mca_api_url", "") or "").strip()
        key = str(setting(self.settings, "mca_api_key", "") or "").strip()
        if not url or not key:
            return {
                "status": "not_configured",
                "source": "licensed corporate registry provider",
                "limitations": [
                    "MCA has no official public API. A licensed data provider must be configured via MCA_API_URL and MCA_API_KEY before registry verification can be attempted."
                ],
                "data": {},
                "observed_at": iso(),
                "confidence": 0.0,
                "independently_verified": False,
            }
        if not consent_registry:
            return {
                "status": "not_attempted",
                "source": "licensed corporate registry provider",
                "limitations": ["Corporate registry consent was not granted; no registry request was made."],
                "data": {},
                "observed_at": iso(),
                "confidence": 0.0,
                "independently_verified": False,
            }
        try:
            response = requests.get(
                url,
                params={"corporate_id": corporate_id or "", "company_name": company_name},
                headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
                timeout=self.timeout,
            )
            if response.status_code != 200:
                return {
                    "status": "error",
                    "source": url,
                    "limitations": [f"Registry provider returned HTTP {response.status_code}."],
                    "data": {},
                    "observed_at": iso(),
                    "confidence": 0.0,
                    "independently_verified": False,
                }
            payload = response.json()
            data = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else payload
            if not isinstance(data, dict):
                raise ValueError("registry response was not a JSON object")
            name_value = self._registry_value(data, ("company_name", "legal_name", "entity_name", "name"))
            id_value = self._registry_value(data, ("cin", "corporate_id", "registration_number", "llpin"))
            status_value = self._registry_value(data, ("status", "company_status"))
            name_match = (
                normalise_company_name(name_value) == normalise_company_name(company_name) if name_value else None
            )
            id_match = (
                str(id_value).strip().lower() == str(corporate_id).strip().lower()
                if id_value and corporate_id
                else None
            )
            active = (
                str(status_value).strip().lower() not in REGISTRY_INACTIVE if status_value else None
            )
            confirmed = bool((name_match is True or id_match is True) and active is not False)
            return {
                "status": "ok" if confirmed else "partial",
                "source": url,
                "limitations": [
                    "Registry data is only as reliable as the licensed provider supplying it.",
                    "Absence of a registry match does not prove a company does not exist.",
                ],
                "data": {
                    "registered_name": fact(name_value, source=url, confidence=0.9),
                    "registration_id": fact(id_value, source=url, confidence=0.9),
                    "registry_status": fact(status_value, source=url, confidence=0.9),
                    "name_match": fact(name_match, source=url, confidence=0.9),
                    "id_match": fact(id_match, source=url, confidence=0.9),
                    "confirmed": fact(confirmed, source=url, confidence=0.9),
                },
                "observed_at": iso(),
                "confidence": 0.9 if confirmed else 0.4,
                "independently_verified": bool(confirmed),
            }
        except Exception as exc:
            return {
                "status": "error",
                "source": "licensed corporate registry provider",
                "limitations": [f"Registry lookup failed: {type(exc).__name__}: {exc}"],
                "data": {},
                "observed_at": iso(),
                "confidence": 0.0,
                "independently_verified": False,
            }

    def verify(
        self,
        company_name: str,
        website_url: str | None = None,
        corporate_id: str | None = None,
        consent_external: bool = False,
        consent_registry: bool = False,
    ) -> dict[str, Any]:
        fingerprint = company_fingerprint(company_name)
        base = {
            "status": "ok",
            "company_name": company_name,
            "company_fingerprint": fingerprint,
            "checked_at": iso(),
            "from_cache": False,
            "website": {"status": "not_attempted", "url": website_url, "limitations": []},
            "domain_intelligence": None,
            "registry": {
                "status": "not_attempted",
                "limitations": ["External lookups were not consented to."],
                "data": {},
            },
            "evidence": [],
            "contradictions": [],
            "missing_evidence": [],
            "limitations": [],
            "indicators": [],
            "sources_attempted": [],
            "sources_succeeded": [],
        }

        cached = self._cached(fingerprint)
        if cached is not None:
            cached.update({"from_cache": True, "status": "ok"})
            cached.setdefault("limitations", []).append("Reused cached company verification; no new external requests were made.")
            return cached

        if not consent_external:
            base.update(
                {
                    "status": "not_attempted",
                    "verification_status": "not_attempted",
                    "sources_attempted": [],
                }
            )
            base["limitations"].append(
                "External website, RDAP and registry lookups were not attempted because consent_external was not granted."
            )
            base["missing_evidence"].append("Consent for external corroboration was not provided.")
            base["indicators"].append(
                make_indicator(
                    name="company_external_verification_not_attempted",
                    status="missing",
                    severity=0.0,
                    description="No external corroboration was attempted; consent was not granted.",
                    source="consent gate",
                    confidence=0.9,
                )
            )
            return base

        limitations: list[str] = []
        tokens = _company_tokens(company_name)
        website_data: dict[str, Any] = {"status": "not_attempted", "url": website_url}
        overlap_ratio: float | None = None
        email_consistency: bool | None = None

        if website_url:
            base["sources_attempted"].extend(["safe website fetch", "domain intelligence"])
            fetch = self.fetcher.fetch(website_url)
            website_data = {
                "status": fetch.get("status"),
                "url": website_url,
                "final_url": fetch.get("final_url"),
                "http_status": fetch.get("http_status"),
                "body_preview": fetch.get("body_preview", "")[:500],
                "limitations": list(fetch.get("limitations") or []) + list(fetch.get("errors") or []),
            }
            if fetch.get("status") == "ok":
                base["sources_succeeded"].append("safe website fetch")
                markup = str(fetch.get("body_preview") or "")
                title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", markup)
                title = html.unescape(title_match.group(1)) if title_match else ""
                corpus = " ".join([title, _meta_description(markup), _visible_text(markup)]).lower()
                corpus_tokens = set(re.findall(r"[a-z0-9]+", corpus))
                matched = [token for token in tokens if token in corpus_tokens]
                overlap_ratio = (len(matched) / len(tokens)) if tokens else None

                website_domain = registrable_domain(fetch.get("final_url") or website_url)
                found_emails = dedupe(email.lower() for email in EMAIL_RE.findall(markup))
                business_domains = [
                    registrable_domain(email.rsplit("@", 1)[-1])
                    for email in found_emails
                    if email.rsplit("@", 1)[-1] not in PERSONAL_EMAIL_DOMAINS
                ]
                business_domains = [domain for domain in dedupe(business_domains) if domain]
                if not business_domains:
                    email_consistency = None
                elif website_domain and all(domain == website_domain for domain in business_domains):
                    email_consistency = True
                else:
                    email_consistency = False

                website_data["overlap"] = {
                    "company_tokens": tokens,
                    "matched_tokens": matched,
                    "ratio": overlap_ratio,
                    "source": fetch.get("final_url"),
                    "observed_at": iso(),
                    "confidence": 0.7,
                    "limitations": ["Text-only rendering; JavaScript-generated content is not visible."],
                }
                website_data["email_domains"] = business_domains
                website_data["email_consistency"] = email_consistency

                if matched:
                    base["evidence"].append(
                        {
                            "claim": "company name appears on the supplied website",
                            "value": ", ".join(matched),
                            "source": fetch.get("final_url"),
                            "observed_at": iso(),
                            "confidence": round(0.4 + 0.4 * (overlap_ratio or 0), 3),
                            "limitations": ["Text overlap can be copied; it is not independent identity verification."],
                        }
                    )
                else:
                    base["contradictions"].append(
                        {
                            "claim": "company name tokens absent from supplied website text",
                            "source": fetch.get("final_url"),
                            "observed_at": iso(),
                            "confidence": 0.35,
                            "limitations": ["A minimal or JavaScript-only site may contain no extractable text."],
                        }
                    )
                if email_consistency is True:
                    base["evidence"].append(
                        {
                            "claim": "website email addresses use the website domain",
                            "value": ", ".join(business_domains),
                            "source": fetch.get("final_url"),
                            "observed_at": iso(),
                            "confidence": 0.6,
                            "limitations": ["Anyone can host a matching email address on their own domain."],
                        }
                    )
                elif email_consistency is False:
                    base["contradictions"].append(
                        {
                            "claim": "website email addresses use a different domain",
                            "value": ", ".join(business_domains),
                            "source": fetch.get("final_url"),
                            "observed_at": iso(),
                            "confidence": 0.45,
                            "limitations": ["Third-party recruiting and shared mail providers are common and not proof of fraud."],
                        }
                    )
            else:
                limitations.append(f"Website text was not retrieved: {'; '.join(website_data['limitations']) or 'unknown error'}")
        else:
            base["missing_evidence"].append("No website URL was supplied for corroboration.")

        domain_intel = self.domain_analyser.analyse(website_url) if website_url else {
            "status": "not_attempted",
            "source": "domain analysis",
            "limitations": ["No website URL was supplied."],
            "data": {},
            "indicators": [],
        }
        base["domain_intelligence"] = domain_intel
        for indicator in domain_intel.get("indicators") or []:
            base["indicators"].append(indicator)
        if (domain_intel.get("signals") or {}).get("domain_age_days", {}).get("value") is None:
            base["missing_evidence"].append("Domain registration age was not available.")

        registry = self._registry(company_name, corporate_id, consent_registry)
        base["registry"] = registry
        if registry.get("status") not in {"not_configured", "not_attempted"}:
            base["sources_attempted"].append("licensed corporate registry provider")
        if registry.get("status") == "ok":
            base["sources_succeeded"].append("licensed corporate registry provider")
            base["evidence"].append(
                {
                    "claim": "registry record matches the supplied company",
                    "value": {
                        "registered_name": (registry["data"]["registered_name"] or {}).get("value"),
                        "registration_id": (registry["data"]["registration_id"] or {}).get("value"),
                    },
                    "source": registry.get("source"),
                    "observed_at": iso(),
                    "confidence": 0.9,
                    "limitations": registry.get("limitations", []),
                }
            )
        elif registry.get("status") == "not_configured":
            base["missing_evidence"].append("No licensed corporate registry provider is configured.")
        elif registry.get("status") == "not_attempted":
            base["missing_evidence"].append("Corporate registry consent was not granted.")
        elif registry.get("status") == "partial":
            base["contradictions"].append(
                {
                    "claim": "registry record did not confirm the supplied company",
                    "source": registry.get("source"),
                    "observed_at": iso(),
                    "confidence": 0.5,
                    "limitations": registry.get("limitations", []),
                }
            )

        registry_confirmed = registry.get("status") == "ok"
        strong_website = overlap_ratio is not None and overlap_ratio >= 0.75 and email_consistency is True
        if registry_confirmed:
            verification_status = "verified_with_evidence"
        elif strong_website or (overlap_ratio is not None and overlap_ratio > 0) or email_consistency is True:
            verification_status = "partial"
        else:
            verification_status = "unverified"

        base["indicators"].extend(
            [
                make_indicator(
                    name="company_registry_confirmation" if registry_confirmed else "company_registry_not_confirmed",
                    status="supportive" if registry_confirmed else ("missing" if registry.get("status") in {"not_configured", "not_attempted"} else "unverified"),
                    severity=0.0 if registry_confirmed else (0.0 if registry.get("status") in {"not_configured", "not_attempted"} else 0.25),
                    description=(
                        "A licensed registry record matched the supplied company name or identifier."
                        if registry_confirmed
                        else str((registry.get("limitations") or ["Registry confirmation was unavailable."])[0])
                    ),
                    source=registry.get("source", "licensed corporate registry provider"),
                    confidence=0.9 if registry_confirmed else 0.4,
                    independently_verified=registry_confirmed,
                ),
                make_indicator(
                    name="company_website_name_overlap" if overlap_ratio else "company_website_name_absent",
                    status="supportive" if overlap_ratio else "unverified",
                    severity=0.0 if overlap_ratio else 0.15,
                    description=(
                        f"{round(overlap_ratio * 100)}% of company-name tokens appeared in website text."
                        if overlap_ratio is not None
                        else "No company-name token overlap could be assessed."
                    ),
                    source=(website_data.get("final_url") or website_url or "no website supplied"),
                    confidence=0.6 if overlap_ratio is not None else 0.3,
                ),
            ]
        )
        if email_consistency is False:
            base["indicators"].append(
                make_indicator(
                    name="company_email_domain_mismatch",
                    status="unverified",
                    severity=0.2,
                    description="Email addresses published on the website use a domain different from the website domain; third-party recruiting remains a common legitimate explanation.",
                    source=website_data.get("final_url") or website_url,
                    confidence=0.4,
                )
            )

        base["verification_status"] = verification_status
        base["status"] = "limited" if limitations else "ok"
        base["limitations"].extend(limitations)
        base["website"] = website_data
        base["limitations"].append("Text-only website analysis cannot see JavaScript-rendered or image-only content.")
        base["limitations"].append("A company name match is not a claim that a particular recruiter is authorised.")

        repo = getattr(self.repos, "companies", None) if self.repos is not None else None
        if repo is not None and fingerprint:
            try:
                repo.upsert(fingerprint, base)
            except Exception as exc:
                base["limitations"].append(f"Company cache write failed: {type(exc).__name__}: {exc}")
        return base


__all__ = ["CompanyVerifier"]
