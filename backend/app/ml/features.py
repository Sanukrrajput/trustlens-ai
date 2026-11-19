"""Text normalisation and anomaly feature contracts shared by training and inference.

Every transformation here is deterministic and side-effect free so that the exact
same code path can be used offline (training) and online (inference). This avoids
the most common source of train/serve skew in fraud-detection systems.

The anomaly feature vocabulary is intentionally small and explainable. It mixes
content-derived signals (length, urgency language, payment demands) with
contextual signals supplied by other subsystems (domain age, company registry,
reputation). Missing contextual values are treated as neutral zeroes rather than
being invented, and every model built on these features must document that its
performance depends on those upstream lookups being available.
"""

from __future__ import annotations

import html
import re
import unicodedata
from typing import Any, Mapping

import numpy as np

URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\-\s().]{7,}\d)(?!\w)")
HTML_TAG_RE = re.compile(r"<[^>]+>")
DIGIT_RE = re.compile(r"\d+")
PUNCTUATION_RE = re.compile(r"[^a-z0-9\s]+")
WHITESPACE_RE = re.compile(r"\s+")

# Lexicons are intentionally conservative: they are used as weak signals and as
# human-readable explanations, never as conclusive proof of fraud.
URGENCY_TERMS = (
    "urgent",
    "immediately",
    "act now",
    "limited time",
    "today only",
    "hurry",
    "asap",
    "deadline",
    "walk-in",
    "same day",
)
PAYMENT_TERMS = (
    "wire transfer",
    "western union",
    "moneygram",
    "gift card",
    "processing fee",
    "registration fee",
    "training fee",
    "security deposit",
    "advance payment",
    "upfront payment",
    "bank details",
    "bank account",
    "account number",
    "routing number",
    "bitcoin",
    "crypto",
    "paypal friends",
)
PERSONAL_DATA_TERMS = (
    "social security",
    "ssn",
    "aadhaar",
    "passport",
    "cvv",
    "date of birth",
    "pan card",
    "identity proof",
)
WORK_FROM_HOME_TERMS = (
    "work from home",
    "work from anywhere",
    "earn from home",
    "no experience",
    "telecommute",
    "remote position",
    "part time",
)

ANOMALY_FEATURE_NAMES: tuple[str, ...] = (
    "text_length",
    "word_count",
    "url_count",
    "email_count",
    "phone_count",
    "urgency_terms",
    "payment_terms",
    "personal_data_terms",
    "work_from_home_terms",
    "exclamation_count",
    "caps_ratio",
    "salary_missing",
    "company_logo_missing",
    "has_questions_missing",
    "telecommuting",
    "domain_age_days",
    "domain_reputation_score",
    "company_age_years",
    "reported_scam_count",
    "duplicate_post_count",
    "link_shortener_count",
    "attachment_count",
    "sender_domain_mismatch",
    "message_hour_oddity",
)

# Bounds keep a single malformed upstream value from dominating an anomaly score.
# Counts are capped at 50; ratios and reputation-style scores stay in [0, 1].
FEATURE_BOUNDS: dict[str, tuple[float, float]] = {
    **{name: (0.0, 50.0) for name in ANOMALY_FEATURE_NAMES[:11]},
    "text_length": (0.0, 20_000.0),
    "word_count": (0.0, 5_000.0),
    "caps_ratio": (0.0, 1.0),
    "salary_missing": (0.0, 1.0),
    "company_logo_missing": (0.0, 1.0),
    "has_questions_missing": (0.0, 1.0),
    "telecommuting": (0.0, 1.0),
    "domain_age_days": (0.0, 3650.0),
    "domain_reputation_score": (0.0, 1.0),
    "company_age_years": (0.0, 100.0),
    "reported_scam_count": (0.0, 50.0),
    "duplicate_post_count": (0.0, 50.0),
    "link_shortener_count": (0.0, 50.0),
    "attachment_count": (0.0, 50.0),
    "sender_domain_mismatch": (0.0, 1.0),
    "message_hour_oddity": (0.0, 1.0),
}

# Accepted aliases from callers in other subsystems. Canonical names always win.
FEATURE_ALIASES: dict[str, str] = {
    "domain_age": "domain_age_days",
    "age_days": "domain_age_days",
    "reputation": "domain_reputation_score",
    "reputation_score": "domain_reputation_score",
    "domain_reputation": "domain_reputation_score",
    "company_age": "company_age_years",
    "logo_missing": "company_logo_missing",
    "questions_missing": "has_questions_missing",
    "prior_reports": "reported_scam_count",
    "scam_reports": "reported_scam_count",
    "duplicates": "duplicate_post_count",
    "shorteners": "link_shortener_count",
    "attachments": "attachment_count",
    "sender_mismatch": "sender_domain_mismatch",
    "odd_hour": "message_hour_oddity",
}


def _count_terms(haystack: str, terms: tuple[str, ...]) -> float:
    """Count non-overlapping occurrences of a small phrase lexicon."""
    return float(sum(haystack.count(term) for term in terms))


def normalize_text(text: str | None) -> str:
    """Normalise HTML-heavy recruitment text into a stable, lowercase document.

    URLs, e-mail addresses and phone numbers are replaced with sentinel tokens so
    that models learn the *presence* of a contact channel rather than memorising
    particular addresses. Digits are collapsed to a single sentinel as well.
    """
    if not text:
        return ""
    value = unicodedata.normalize("NFKC", str(text))
    value = html.unescape(value)
    value = HTML_TAG_RE.sub(" ", value)
    value = URL_RE.sub(" URLTOKEN ", value)
    value = EMAIL_RE.sub(" EMAILTOKEN ", value)
    value = PHONE_RE.sub(" PHONETOKEN ", value)
    value = DIGIT_RE.sub(" NUMTOKEN ", value)
    value = PUNCTUATION_RE.sub(" ", value.lower())
    return WHITESPACE_RE.sub(" ", value).strip()


def text_signal_counts(text: str | None) -> dict[str, float]:
    """Return interpretable content signals for a raw (unnormalised) text."""
    raw = str(text or "")
    normalised = normalize_text(raw)
    letters = [char for char in raw if char.isalpha()]
    caps_ratio = (sum(1 for char in letters if char.isupper()) / len(letters)) if letters else 0.0
    return {
        "text_length": float(min(len(raw), 100_000)),
        "word_count": float(len(normalised.split())),
        "url_count": float(len(URL_RE.findall(raw))),
        "email_count": float(len(EMAIL_RE.findall(raw))),
        "phone_count": float(len(PHONE_RE.findall(raw))),
        "urgency_terms": _count_terms(normalised, URGENCY_TERMS),
        "payment_terms": _count_terms(normalised, PAYMENT_TERMS),
        "personal_data_terms": _count_terms(normalised, PERSONAL_DATA_TERMS),
        "work_from_home_terms": _count_terms(normalised, WORK_FROM_HOME_TERMS),
        "exclamation_count": float(raw.count("!")),
        "caps_ratio": caps_ratio,
    }


def build_anomaly_vector(feature_vector: Mapping[str, Any]) -> np.ndarray:
    """Map a caller-supplied mapping onto the fixed, bounded anomaly vocabulary.

    Unknown keys are ignored, aliases are resolved, non-numeric values become 0.0,
    and every value is clipped to its documented range. The result is always a
    1-D ``float64`` array of length ``len(ANOMALY_FEATURE_NAMES)``.
    """
    canonical: dict[str, Any] = {}
    for key, value in (feature_vector or {}).items():
        name = str(key)
        name = FEATURE_ALIASES.get(name, name)
        if name in ANOMALY_FEATURE_NAMES and name not in canonical:
            canonical[name] = value

    vector = np.zeros(len(ANOMALY_FEATURE_NAMES), dtype=np.float64)
    for index, name in enumerate(ANOMALY_FEATURE_NAMES):
        raw = canonical.get(name, 0.0)
        try:
            number = float(raw)
        except (TypeError, ValueError):
            number = 0.0
        if not np.isfinite(number):
            number = 0.0
        low, high = FEATURE_BOUNDS[name]
        vector[index] = float(np.clip(number, low, high))
    return vector


def anomaly_feature_dict(feature_vector: Mapping[str, Any]) -> dict[str, float]:
    """Return a canonical, JSON-friendly name -> value mapping for explanations."""
    vector = build_anomaly_vector(feature_vector)
    return {name: float(value) for name, value in zip(ANOMALY_FEATURE_NAMES, vector)}
