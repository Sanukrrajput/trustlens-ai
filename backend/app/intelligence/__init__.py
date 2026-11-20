"""Explainable, evidence-first intelligence helpers for TrustLens AI.

Nothing in this package decides that a person or company is fraudulent. Every
finding is an *indicator* with a source, an observation time, a confidence and
explicit limitations. Absence of evidence is reported as missing evidence, not
as evidence of wrongdoing.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from urllib.parse import urlsplit

EVIDENCE_STATUSES = frozenset(
    {
        "confirmed_malicious",
        "verified_inconsistency",
        "suspicious",
        "unverified",
        "missing",
        "technical_limitation",
        "supportive",
    }
)

# Consumer mail providers. Used only to avoid mistaking a personal address for
# a company domain; a personal address is never presented as proof of fraud.
PERSONAL_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "yahoo.co.in",
        "yahoo.in",
        "hotmail.com",
        "hotmail.co.in",
        "outlook.com",
        "outlook.in",
        "live.com",
        "live.in",
        "msn.com",
        "icloud.com",
        "me.com",
        "aol.com",
        "proton.me",
        "protonmail.com",
        "gmx.com",
        "rediffmail.com",
        "indiatimes.com",
        "mail.com",
        "zoho.com",
        "yandex.com",
        "yandex.ru",
        "qq.com",
        "163.com",
    }
)

MULTI_PART_SUFFIXES = (
    "co.in",
    "com.in",
    "net.in",
    "org.in",
    "firm.in",
    "gen.in",
    "ind.in",
    "res.in",
    "co.uk",
    "org.uk",
    "ac.in",
    "edu.in",
    "gov.in",
    "nic.in",
    "com.au",
    "net.au",
    "org.au",
    "co.nz",
    "co.za",
    "com.sg",
    "com.br",
    "co.jp",
    "com.cn",
    "com.hk",
    "co.id",
    "com.my",
    "com.ph",
    "com.pk",
    "co.ke",
    "co.il",
    "com.tr",
)

LEGAL_SUFFIXES = (
    "private limited",
    "pvt ltd",
    "pvt. ltd",
    "private ltd",
    "limited liability partnership",
    "limited",
    "ltd",
    "llp",
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "plc",
    "gmbh",
    "pvt",
    "company",
    "co",
)

BRAND_NAMES = (
    "google",
    "microsoft",
    "sbi",
    "statebankofindia",
    "hdfc",
    "icici",
    "amazon",
    "flipkart",
    "naukri",
    "linkedin",
    "paytm",
)

# Homoglyph substitutions used only by the clearly-labelled lookalike heuristic.
HOMOGLYPHS = str.maketrans(
    {
        "0": "o",
        "1": "l",
        "3": "e",
        "4": "a",
        "5": "s",
        "7": "t",
        "8": "b",
        "$": "s",
        "!": "i",
        "|": "l",
    }
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: datetime | None = None) -> str:
    """Return an ISO-8601 UTC timestamp string (safe for JSON and MongoDB)."""
    value = moment or utcnow()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def clamp(value: Any, low: float = 0.0, high: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return low
    if number != number:  # NaN
        return low
    return max(low, min(high, number))


def dedupe(values: Iterable[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        key = str(value).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def make_indicator(
    *,
    name: str,
    status: str,
    severity: float,
    description: str,
    source: str,
    reference_url: str | None = None,
    observed_at: str | None = None,
    confidence: float = 0.5,
    independently_verified: bool = False,
    expires_at: str | None = None,
    weight: float = 1.0,
    signal_category: str = "content",
) -> dict[str, Any]:
    """Build an EvidenceIndicator-shaped dict with valid, bounded fields.

    ``signal_category`` is the risk-engine bucket (content, url, brand, threat or
    community). It is metadata for explainability and deterministic scoring; it
    never changes the underlying observation.
    """
    if status not in EVIDENCE_STATUSES:
        status = "unverified"
    return {
        "name": str(name).strip() or "unnamed_indicator",
        "status": status,
        "severity": round(clamp(severity), 3),
        "description": str(description).strip(),
        "source": str(source).strip() or "rule",
        "reference_url": reference_url or None,
        "observed_at": observed_at or iso(),
        "confidence": round(clamp(confidence), 3),
        "independently_verified": bool(independently_verified),
        "expires_at": expires_at,
        "weight": round(clamp(weight, 0.0, 2.0), 3),
        "signal_category": signal_category if signal_category in {"content", "url", "brand", "threat", "community", "coverage"} else "content",
    }


def fact(
    value: Any,
    *,
    source: str,
    confidence: float = 0.6,
    observed_at: str | None = None,
    independently_verified: bool = False,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    """Wrap a single observed value with its provenance and caveats."""
    return {
        "value": value,
        "source": source,
        "observed_at": observed_at or iso(),
        "confidence": round(clamp(confidence), 3),
        "independently_verified": bool(independently_verified),
        "limitations": list(limitations or []),
    }


def normalise_company_name(name: Any) -> str:
    text = str(name or "").lower().strip()
    text = re.sub(r"[^a-z0-9&\s.-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .-")
    changed = True
    while changed:
        changed = False
        for suffix in LEGAL_SUFFIXES:
            pattern = rf"\b{re.escape(suffix)}\b\.?$"
            if re.search(pattern, text):
                text = re.sub(pattern, "", text).strip(" .,-&")
                changed = True
    return text


def company_fingerprint(name: Any) -> str:
    normalised = normalise_company_name(name)
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest() if normalised else ""


def normalise_email(email: Any) -> str:
    return str(email or "").strip().lower()


def email_fingerprint(email: Any) -> str:
    value = normalise_email(email)
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else ""


def extract_host(value: Any) -> str:
    """Return a lower-case hostname for a URL or bare host, without port/www."""
    text = str(value or "").strip()
    if not text:
        return ""
    if "//" not in text and re.match(r"^[a-z0-9.-]+(:\d+)?(?:/|$)", text, re.I):
        text = "http://" + text
    try:
        parts = urlsplit(text)
        host = (parts.hostname or "").strip().lower().rstrip(".")
    except ValueError:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def registrable_domain(value: Any) -> str:
    """Best-effort eTLD+1 approximation without an external suffix list."""
    host = extract_host(value)
    if not host:
        return ""
    try:
        ipaddress.ip_address(host)
        return ""
    except ValueError:
        pass
    labels = [label for label in host.split(".") if label]
    if len(labels) < 2:
        return host
    tail = ".".join(labels[-2:])
    if tail in MULTI_PART_SUFFIXES:
        if len(labels) < 3:
            return host
        return ".".join(labels[-3:])
    return tail


def is_public_ip(value: Any) -> bool:
    """True only for a globally routable unicast IP suitable for egress."""
    text = str(value or "").strip().split("%", 1)[0]
    if not text:
        return False
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return bool(
        address.is_global
        and not address.is_private
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_multicast
        and not address.is_unspecified
        and not address.is_reserved
    )


def levenshtein(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for index, char_left in enumerate(left, start=1):
        current = [index]
        for column, char_right in enumerate(right, start=1):
            cost = 0 if char_left == char_right else 1
            current.append(min(current[-1] + 1, previous[column] + 1, previous[column - 1] + cost))
        previous = current
    return previous[-1]


def homoglyph_normalise(text: str) -> str:
    value = str(text or "").lower().translate(HOMOGLYPHS)
    value = value.replace("rn", "m").replace("vv", "w")
    return re.sub(r"[^a-z]", "", value)


def setting(settings: Any, name: str, default: Any) -> Any:
    """Read a setting from a Settings object or a lightweight test stub."""
    value = getattr(settings, name, default)
    return default if value is None else value


def expiry_from_now(hours: float) -> str:
    return iso(utcnow() + timedelta(hours=hours))


__all__ = [
    "BRAND_NAMES",
    "EVIDENCE_STATUSES",
    "PERSONAL_EMAIL_DOMAINS",
    "clamp",
    "company_fingerprint",
    "dedupe",
    "email_fingerprint",
    "expiry_from_now",
    "extract_host",
    "fact",
    "homoglyph_normalise",
    "is_public_ip",
    "iso",
    "levenshtein",
    "make_indicator",
    "normalise_company_name",
    "normalise_email",
    "registrable_domain",
    "setting",
    "utcnow",
]
