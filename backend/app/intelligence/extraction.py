"""Conservative regex-based entity extraction for job posts and messages.

The extractor deliberately under-claims: a missing entity is reported as an
empty value, never guessed. It has no network access and no ML component.
"""

from __future__ import annotations

import re
from typing import Any

from app.intelligence import (
    PERSONAL_EMAIL_DOMAINS,
    company_fingerprint,
    dedupe,
    extract_host,
    registrable_domain,
)

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
URL_RE = re.compile(r"\b(?:https?://|www\.)[^\s<>\"']+", re.I)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\s\-.]?)?(?:0[\s\-.]?)?[6-9]\d{4}[\s\-.]?\d{5}(?!\d)")

KNOWN_TITLES = (
    "senior software engineer",
    "software engineer",
    "senior data analyst",
    "data analyst",
    "data scientist",
    "full stack developer",
    "frontend developer",
    "backend developer",
    "devops engineer",
    "qa engineer",
    "product manager",
    "project manager",
    "program manager",
    "business development manager",
    "human resources manager",
    "hr manager",
    "recruiter",
    "talent acquisition specialist",
    "marketing manager",
    "sales executive",
    "customer support executive",
    "operations manager",
    "account manager",
    "finance manager",
    "graduate engineer",
    "engineering intern",
    "intern",
)

INDIAN_LOCATIONS = (
    "mumbai",
    "delhi",
    "new delhi",
    "ncr",
    "bengaluru",
    "bangalore",
    "hyderabad",
    "chennai",
    "kolkata",
    "pune",
    "ahmedabad",
    "gurugram",
    "gurgaon",
    "noida",
    "jaipur",
    "kochi",
    "kozhikode",
    "chandigarh",
    "indore",
    "nagpur",
    "surat",
    "vadodara",
    "lucknow",
    "kanpur",
    "bhopal",
    "patna",
    "coimbatore",
    "visakhapatnam",
    "thiruvananthapuram",
    "mangaluru",
    "mysuru",
    "faridabad",
    "ghaziabad",
    "navi mumbai",
    "thane",
)

COMPANY_STOPWORDS = {
    "we",
    "our",
    "you",
    "your",
    "the",
    "this",
    "that",
    "dear",
    "congratulations",
    "urgent",
    "immediate",
    "job",
    "jobs",
    "position",
    "role",
    "salary",
    "location",
    "company",
    "about",
    "apply",
    "hiring",
    "candidate",
    "team",
    "hello",
    "hi",
    "sir",
    "madam",
    "greetings",
    "greeting",
}

PAYMENT_PATTERNS = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"\b(?:registration|processing|application|training|placement|security|joining|interview|verification|refundable)\s+fee\b",
        r"\bpay\s+(?:₹|rs\.?|inr)?\s*\d",
        r"\b(?:transfer|send|remit|deposit)\s+(?:₹|rs\.?|inr)?\s*\d",
        r"\b(?:upi\s*(?:id)?|paytm|phonepe|google\s*pay|bank\s*transfer|neft|imps|rtgs|demand\s*draft)\b",
        r"\b(?:advance\s*payment|service\s*charge|subscription\s*fee|money\s*transfer|gift\s*card)\b",
    )
)

SENSITIVE_PATTERNS = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"\b(?:otp|one[\s-]time[\s-]password|cvv|card\s*pin|password|aadhaar|aadhar|pan\s*card|bank\s*account|net\s*banking|debit\s*card|credit\s*card|passport|photo\s*id|id\s*proof|documents?)\b",
    )
)
REQUEST_VERBS = re.compile(
    r"\b(?:share|send|submit|provide|upload|give|verify|confirm|furnish|attach|required|needed|copy|copies)\b",
    re.I,
)


def _clean_snippet(value: str, limit: int = 200) -> str:
    text = re.sub(r"\s+", " ", value or "").strip(" \t\r\n-:;|>")
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def _sentences(text: str) -> list[str]:
    pieces = re.split(r"(?<=[.!?])\s+|\n+|\s*[;|]\s*", text)
    return [_clean_snippet(piece) for piece in pieces if _clean_snippet(piece)]


def _candidate_company(value: str) -> str:
    text = _clean_snippet(value, 120)
    text = re.split(r"\s+(?:is|are|was|has|offers|based|located|was)\s+", text, maxsplit=1, flags=re.I)[0]
    text = re.split(r"\s*[|•]\s*", text, maxsplit=1)[0]
    text = re.sub(r"^(?:the|our|we|at|from|about)\s+", "", text, flags=re.I)
    text = text.strip(" .,:;-|\"'")
    tokens = text.split()
    if not tokens or len(tokens) > 7:
        return ""
    if tokens[0].lower() in COMPANY_STOPWORDS:
        return ""
    if len(text) < 3 or not re.search(r"[A-Za-z]{3}", text):
        return ""
    if text.lower() in {title.lower() for title in KNOWN_TITLES}:
        return ""
    return text


def _companies(text: str) -> list[str]:
    found: list[str] = []
    for line in text.splitlines():
        labelled = re.search(
            r"\b(?:company|organisation|organization|employer|client)\s*(?:name)?\s*[:\-]\s*(.+)$",
            line,
            re.I,
        )
        if labelled:
            candidate = _candidate_company(labelled.group(1))
            if candidate:
                found.append(candidate)
        hiring = re.search(
            r"\b([A-Z][A-Za-z0-9&.'\-]*(?:\s+[A-Z][A-Za-z0-9&.'\-]*){0,4})\s+(?:is|are)\s+hiring\b",
            line,
        )
        if hiring:
            candidate = _candidate_company(hiring.group(1))
            if candidate:
                found.append(candidate)

    legal_suffix = (
        r"\b([A-Z][A-Za-z0-9&.'\-]*(?:\s+(?:[A-Z][A-Za-z0-9&.'\-]*|of|and|the|for)){0,5}"
        r"\s*(?:pvt\.?\s*)?(?:private\s+limited|ltd\.?|llp|inc\.?|technologies|solutions|services|systems|consulting))\b"
    )
    for match in re.finditer(legal_suffix, text):
        candidate = _candidate_company(match.group(1))
        if candidate:
            found.append(candidate)
    return dedupe(found)[:6]


def _job_titles(text: str, companies: list[str]) -> list[str]:
    found: list[str] = []
    company_keys = {company.lower() for company in companies}
    for line in text.splitlines():
        labelled = re.search(
            r"\b(?:job\s*title|designation|position|role|opening|profile)\s*[:\-]\s*(.{3,60})$",
            line,
            re.I,
        )
        if labelled:
            candidate = _clean_snippet(labelled.group(1), 60)
            if candidate and candidate.lower() not in company_keys:
                found.append(candidate)
    lowered = text.lower()
    for title in KNOWN_TITLES:
        if re.search(rf"\b{re.escape(title)}\b", lowered):
            found.append(title)
    return dedupe(found)[:6]


def _salary(text: str) -> str | None:
    patterns = (
        r"(?:₹|rs\.?|inr)\s?\d[\d,]*(?:\.\d+)?\s*(?:-|to|–)\s*(?:₹|rs\.?|inr)?\s?\d[\d,]*(?:\.\d+)?\s*(?:lpa|lakhs?|crores?|per\s+annum|p\.?a\.?)?",
        r"\b\d+(?:\.\d+)?\s*(?:-|to|–)\s*\d+(?:\.\d+)?\s*(?:lpa|lakhs?(?:\s+per\s+annum)?|crores?)\b",
        r"(?:₹|rs\.?|inr)\s?\d[\d,]*(?:\.\d+)?\s*(?:lpa|lakhs?|crore|per\s+month|per\s+annum|p\.?m\.|p\.?a\.)?",
        r"\b\d+(?:\.\d+)?\s*(?:lpa|lakhs?|crores?)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return _clean_snippet(match.group(0), 100)
    return None


def _phones(text: str) -> list[str]:
    result: list[str] = []
    for match in PHONE_RE.finditer(text):
        candidate = match.group(0).strip()
        digits = re.sub(r"\D", "", candidate)
        if digits.startswith("91") and len(digits) == 12:
            digits = digits[2:]
        elif digits.startswith("0") and len(digits) == 11:
            digits = digits[1:]
        if len(digits) == 10 and digits[0] in "6789":
            result.append(candidate)
    return dedupe(result)[:8]


def _urls(text: str) -> list[str]:
    result: list[str] = []
    for match in URL_RE.finditer(text):
        url = match.group(0).rstrip(".,;:!?)]}>\"'")
        if url.lower().startswith("www."):
            url = "https://" + url
        result.append(url)
    return dedupe(result)[:12]


def _matching_sentences(sentences: list[str], patterns: tuple[re.Pattern[str], ...], require_verb: bool = False) -> list[str]:
    matches: list[str] = []
    for sentence in sentences:
        if any(pattern.search(sentence) for pattern in patterns) and (
            not require_verb or REQUEST_VERBS.search(sentence)
        ):
            matches.append(sentence)
    return dedupe(matches)[:8]


def _locations(text: str) -> list[str]:
    found = [city.title() for city in INDIAN_LOCATIONS if re.search(rf"\b{re.escape(city)}\b", text, re.I)]
    for match in re.finditer(r"\b(?:location|located\s+in|based\s+in|office\s+at)\s*[:\-]\s*([A-Za-z][A-Za-z\s,]{2,40})", text, re.I):
        candidate = _clean_snippet(match.group(1), 40)
        if candidate and not any(part.lower() in COMPANY_STOPWORDS for part in candidate.split()):
            found.append(candidate)
    return dedupe(found)[:6]


def _domain_candidates(emails: list[str], urls: list[str]) -> list[str]:
    hosts: list[str] = []
    for email in emails:
        domain = normalise_email_domain(email)
        if domain:
            hosts.append(domain)
    for url in urls:
        host = extract_host(url)
        if host:
            hosts.append(host)
    candidates: list[str] = []
    for host in hosts:
        domain = registrable_domain(host)
        if not domain or domain in PERSONAL_EMAIL_DOMAINS:
            continue
        if domain in {"localhost", "example.com", "example.invalid"}:
            continue
        candidates.append(domain)
    return dedupe(candidates)[:10]


def normalise_email_domain(email: str) -> str:
    return str(email or "").strip().lower().rsplit("@", 1)[-1] if "@" in str(email or "") else ""


def extract_entities(text: str) -> dict[str, Any]:
    """Extract cautious, explainable entities from unstructured text.

    Returned keys are compatible with ``ExtractedEntities`` plus three
    additional diagnostic keys: ``company_fingerprint``, ``domain_candidates``
    and ``text_stats``.
    """
    source = text if isinstance(text, str) else ("" if text is None else str(text))
    normalised = re.sub(r"[\u00a0\u200b]", " ", source)
    sentences = _sentences(normalised)

    companies = _companies(normalised)
    emails = dedupe(match.group(0).lower() for match in EMAIL_RE.finditer(normalised))[:12]
    urls = _urls(normalised)
    phones = _phones(normalised)
    salary = _salary(normalised)
    payment_demands = _matching_sentences(sentences, PAYMENT_PATTERNS)
    sensitive = _matching_sentences(sentences, SENSITIVE_PATTERNS, require_verb=True)
    locations = _locations(normalised)

    words = re.findall(r"\b\w+\b", normalised)
    stats = {
        "word_count": len(words),
        "char_count": len(normalised),
        "sentence_count": len(sentences),
        "line_count": len(normalised.splitlines()) if normalised else 0,
        "has_urls": bool(urls),
        "has_emails": bool(emails),
        "has_phone": bool(phones),
        "has_payment_language": bool(payment_demands),
        "has_sensitive_data_request": bool(sensitive),
    }

    return {
        "company_names": companies,
        "job_titles": _job_titles(normalised, companies),
        "salary": salary,
        "recruiter_emails": emails,
        "phone_numbers": phones,
        "urls": urls,
        "payment_demands": payment_demands,
        "sensitive_data_requests": sensitive,
        "locations": locations,
        "company_fingerprint": company_fingerprint(companies[0]) if companies else "",
        "domain_candidates": _domain_candidates(emails, urls),
        "text_stats": stats,
    }


__all__ = ["extract_entities", "normalise_email_domain"]
