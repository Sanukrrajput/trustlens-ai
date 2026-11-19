"""Explainable, rule-based analysis of recruitment messages.

This analyser detects *patterns*, not perpetrators. A single weak pattern is
never sufficient to describe a sender or company as fraudulent.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any
from urllib.parse import urlsplit

from app.intelligence import PERSONAL_EMAIL_DOMAINS, dedupe, iso, make_indicator, registrable_domain

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
URL_RE = re.compile(
    r"\b(?:https?://|www\.)[^\s<>\"']+"
    r"|\b(?:bit\.ly|tinyurl\.com|t\.co|goo\.gl|is\.gd|ow\.ly|s\.id|cutt\.ly|rebrand\.ly)/[^\s<>\"']+",
    re.I,
)
SHORTENERS = {
    "bit.ly",
    "tinyurl.com",
    "t.co",
    "goo.gl",
    "is.gd",
    "ow.ly",
    "s.id",
    "cutt.ly",
    "rebrand.ly",
    "tiny.ly",
}

PATTERNS: dict[str, tuple[tuple[str, float, str], ...]] = {
    "fee_demand": (
        (r"\b(?:registration|processing|application|training|placement|security|joining|interview|verification|refundable)\s+fee\b", 0.75, "registration/processing fee"),
        (r"\b(?:pay|transfer|send|remit|deposit)\s+(?:₹|rs\.?|inr)?\s*\d[\d,]*", 0.7, "direct payment demand"),
        (r"\b(?:advance\s*payment|service\s*charge|subscription\s*fee|gift\s*card|money\s*transfer)\b", 0.6, "advance/service charge"),
        (r"\b(?:upi\s*(?:id)?|paytm|phonepe|google\s*pay|bank\s*transfer|neft|imps|rtgs|demand\s*draft)\b", 0.55, "Indian payment instruction"),
    ),
    "sensitive_data_request": (
        (r"\b(?:otp|one[\s-]time[\s-]password|cvv|card\s*pin|net\s*banking|bank\s*account\s*(?:number|details)?)\b", 0.85, "OTP/banking credential request"),
        (r"\b(?:aadhaar|aadhar|pan\s*card|passport|photo\s*id|id\s*proof)\b", 0.6, "identity document request"),
        (r"\b(?:password|debit\s*card|credit\s*card)\b", 0.75, "credential or card request"),
    ),
    "urgency_pressure": (
        (r"\b(?:urgent|immediately|asap|hurry|act\s+fast|last\s+chance|final\s+chance|don'?t\s+miss)\b", 0.4, "urgency wording"),
        (r"\b(?:today\s+only|within\s+\d+\s*(?:hours|days)|before\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?|confirm\s+by|limited\s+(?:slots|time))\b", 0.45, "deadline pressure"),
    ),
    "fake_offer_letter": (
        (r"\b(?:offer\s+letter|appointment\s+letter|joining\s+letter|selection\s+letter|formal\s+offer)\b", 0.45, "offer letter reference"),
        (r"\b(?:congratulations[^\n]{0,80}(?:selected|shortlisted)|you\s+(?:are|have\s+been)\s+selected|direct\s+selection)\b", 0.5, "selection claim"),
        (r"\bdownload[^\n]{0,60}(?:offer|appointment|joining)\b", 0.5, "offer download instruction"),
    ),
    "document_submission": (
        (r"\b(?:submit|upload|send|share)[^.\n]{0,60}\b(?:documents?|certificates?|resume|cv|id\s*proof|photo)\b", 0.45, "document submission instruction"),
        (r"\b(?:educational\s+certificates?|passport\s*size\s*photo|photocopy\s+of)\b", 0.4, "document copy request"),
    ),
    "whatsapp_sms_patterns": (
        (r"\b(?:wa\.me|whatsapp|sms|text\s+me|message\s+me\s+on|forwarded)\b", 0.35, "messaging-channel reference"),
        (r"\b(?:dear\s+candidate|hi\s+sir|good\s+morning|kindly|do\s+the\s+needful|plz|pls)\b", 0.25, "informal recruiting message phrasing"),
    ),
    "unverified_claims": (
        (r"\b(?:guaranteed\s+job|100%\s+placement|no\s+interview|without\s+interview|earn\s+(?:₹|rs\.?|inr)?\s*\d+[^\n]{0,20}per\s+day)\b", 0.45, "placement/earnings claim"),
        (r"\b(?:work\s+from\s+home|part[\s-]time\s+job|no\s+experience\s+required)\b", 0.25, "low-barrier offer claim"),
    ),
}


def _snippet(text: str, start: int, end: int, radius: int = 75) -> str:
    fragment = text[max(0, start - radius) : min(len(text), end + radius)]
    return re.sub(r"\s+", " ", fragment).strip()


def _matches(text: str, patterns: tuple[tuple[str, float, str], ...]) -> tuple[list[str], float]:
    found: list[str] = []
    confidence = 0.0
    for pattern, weight, label in patterns:
        for match in re.finditer(pattern, text, re.I):
            found.append(f"{label}: {_snippet(text, match.start(), match.end())}")
            confidence = max(confidence, weight)
    return dedupe(found)[:8], confidence


class MessageAnalyser:
    """Detect explainable recruitment-fraud-associated message patterns."""

    def __init__(self) -> None:
        self.channel = "unknown"

    @staticmethod
    def _url_findings(text: str) -> list[str]:
        findings: list[str] = []
        for raw in URL_RE.findall(text):
            url = raw.rstrip(".,;:!?)]}>\"'")
            if "://" not in url:
                url = "https://" + url.removeprefix("www.")
            try:
                parts = urlsplit(url)
                host = (parts.hostname or "").lower().rstrip(".")
            except ValueError:
                findings.append(f"{url}: malformed URL")
                continue
            reasons: list[str] = []
            if parts.scheme.lower() not in {"http", "https"}:
                reasons.append("non-web scheme")
            if "@" in parts.netloc:
                reasons.append("URL contains userinfo")
            if host in SHORTENERS or registrable_domain(host) in SHORTENERS:
                reasons.append("URL shortener hides the destination")
            try:
                ipaddress.ip_address(host)
                reasons.append("IP-literal link")
            except ValueError:
                pass
            findings.append(f"{url}: {', '.join(reasons) if reasons else 'link requires destination verification'}")
        return dedupe(findings)[:10]

    def _personal_email_findings(self, text: str, sender: str | None) -> list[str]:
        findings: list[str] = []
        addresses = [match.group(0).lower() for match in EMAIL_RE.finditer(text)]
        if sender:
            addresses.append(sender.strip().lower())
        for address in dedupe(addresses):
            domain = address.rsplit("@", 1)[-1] if "@" in address else ""
            if domain in PERSONAL_EMAIL_DOMAINS:
                findings.append(f"{address}: personal/free email provider")
        return findings[:8]

    def analyse(self, text: str, channel: str = "unknown", sender: str | None = None) -> dict[str, Any]:
        source = text if isinstance(text, str) else ("" if text is None else str(text))
        normalised = re.sub(r"\s+", " ", source)
        signals: dict[str, Any] = {}
        indicators: list[dict[str, Any]] = []

        for name, patterns in PATTERNS.items():
            matches, confidence = _matches(normalised, patterns)
            signals[name] = {
                "detected": bool(matches),
                "matches": matches,
                "confidence": round(confidence if matches else 0.0, 3),
                "explanation": "Matched a small set of transparent, human-readable rules.",
                "source": "local rules",
            }

        url_findings = self._url_findings(normalised)
        signals["phishing_links"] = {
            "detected": bool(url_findings),
            "matches": url_findings,
            "confidence": 0.4 if url_findings else 0.0,
            "explanation": "Links are flagged for destination verification; a link alone is not evidence of phishing.",
            "source": "local URL heuristics",
        }
        email_findings = self._personal_email_findings(normalised, sender)
        signals["personal_email_sender"] = {
            "detected": bool(email_findings),
            "matches": email_findings,
            "confidence": 0.25 if email_findings else 0.0,
            "explanation": "Personal email addresses are common in legitimate small-company recruiting.",
            "source": "local domain heuristic",
        }

        channel_lower = channel.lower()
        if channel_lower in {"whatsapp", "sms", "telegram"}:
            signals["whatsapp_sms_patterns"]["detected"] = True
            signals["whatsapp_sms_patterns"]["matches"].insert(0, f"channel supplied as {channel}")
            signals["whatsapp_sms_patterns"]["confidence"] = max(
                signals["whatsapp_sms_patterns"]["confidence"], 0.3
            )

        amounts = dedupe(re.findall(r"(?:₹|rs\.?|inr)\s*\d[\d,]*", normalised, re.I))
        signals["payment_amounts"] = {
            "detected": bool(amounts),
            "matches": amounts,
            "confidence": 0.6 if amounts else 0.0,
            "explanation": "Amounts were extracted verbatim; no currency normalization is inferred.",
            "source": "local regex",
        }

        indicator_specs = (
            ("fee_demand", "suspicious", 0.55, "The message contains a demand for a fee, advance or transfer. Legitimate employers may charge for optional training, so verify the context."),
            ("sensitive_data_request", "suspicious", 0.6, "The message asks for credentials, OTPs, banking details or identity documents before trust has been established."),
            ("urgency_pressure", "suspicious", 0.25, "Urgency or deadline language can be legitimate but is frequently used to suppress verification."),
            ("fake_offer_letter", "unverified", 0.3, "The message refers to an offer letter or selection without providing independently verifiable details."),
            ("document_submission", "unverified", 0.2, "The message requests documents; confirm the recipient and purpose before sharing."),
            ("phishing_links", "suspicious", 0.4, "Links require destination verification; shortened or IP-literal links hide the real target."),
            ("personal_email_sender", "unverified", 0.2, "A personal/free email address was found; many legitimate recruiters use one."),
            ("whatsapp_sms_patterns", "unverified", 0.15, "Informal messaging patterns were detected; this is a weak contextual signal only."),
            ("unverified_claims", "unverified", 0.25, "Strong placement/earnings claims were made without supporting evidence in the message."),
        )
        for name, status, severity, description in indicator_specs:
            signal = signals[name]
            if signal["detected"]:
                indicators.append(
                    make_indicator(
                        name=f"message_{name}",
                        status=status,
                        severity=severity,
                        description=description,
                        source=signal["source"],
                        confidence=signal["confidence"] or 0.4,
                    )
                )

        strong = [name for name in ("fee_demand", "sensitive_data_request", "phishing_links") if signals[name]["detected"]]
        if len(strong) >= 2:
            summary = (
                "Several patterns commonly associated with recruitment fraud are present "
                f"({', '.join(strong)}). Treat the message as unverified, confirm through an "
                "independent official channel, and do not pay or share credentials on this basis."
            )
        elif strong or any(signal["detected"] for signal in signals.values()):
            summary = (
                "Some patterns that warrant extra care were detected. Evidence is incomplete, "
                "so no conclusion about the sender or any company should be drawn from this message alone."
            )
        else:
            summary = (
                "No strong rule-based fraud patterns were detected in the supplied text. "
                "This is not proof of legitimacy; independent verification is still advisable."
            )

        missing_evidence: list[str] = []
        if not url_findings:
            missing_evidence.append("No link was available to inspect the destination domain.")
        if not sender:
            missing_evidence.append("No sender identity was supplied for consistency checks.")
        missing_evidence.append("No external domain, registry or historical intelligence was consulted in this message-only analysis.")

        return {
            "status": "completed",
            "channel": channel,
            "signals": signals,
            "indicators": indicators,
            "missing_evidence": missing_evidence,
            "summary": summary,
            "limitations": [
                "Rule-based pattern matching cannot establish intent or identity.",
                "A single weak signal is never treated as proof of fraud.",
                "Non-English, image-based and heavily obfuscated messages may not be covered.",
            ],
            "observed_at": iso(),
        }


__all__ = ["MessageAnalyser"]
