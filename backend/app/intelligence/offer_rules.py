"""Transparent, category-aware indicators for generic online offers.

This module deliberately produces *indicators*, never verdicts. It supports the
offer categories in the TrustLens specification (advertisements, giveaways,
scholarships, investments, recruitment, promotions and other offers). Every
observation carries a source, a timestamp, a confidence and the explicit caveat
that a phrase alone cannot establish that a business or campaign is fraudulent.

No trained general-offer model exists in the approved manifest, so these rules
are the honest primary signal for offer submissions. They are deterministic,
reviewable and independently testable.
"""

from __future__ import annotations

import re
from typing import Any

from app.intelligence import make_indicator

OFFER_CATEGORIES = (
    "advertisement",
    "giveaway",
    "scholarship",
    "investment",
    "recruitment",
    "promotion",
    "other",
)

# (name, status, severity, confidence, pattern, explanation)
_GENERIC_PATTERNS: tuple[tuple[str, str, float, float, str, str], ...] = (
    (
        "offer_advance_payment",
        "suspicious",
        0.68,
        0.55,
        r"\b(?:advance\s+payment|processing\s+fee|registration\s+(?:fee|charges)|upfront\s+(?:fee|payment)|security\s+deposit|activation\s+fee)\b",
        "The offer asks for money before any product, service or entitlement is provided.",
    ),
    (
        "offer_credential_request",
        "suspicious",
        0.72,
        0.55,
        r"\b(?:share\s+(?:your\s+)?otp|one[- ]time\s+password|verification\s+code|(?:bank|card|account)\s+pin|pin\s+number|bank\s+(?:account\s+)?(?:details|number)|\bcard\s+(?:number|cvv)|password)\b",
        "The offer requests a secret, credential or payment instrument that should not be shared.",
    ),
    (
        "offer_urgency",
        "suspicious",
        0.42,
        0.45,
        r"\b(?:act\s+now|limited\s+time|last\s+chance|today\s+only|expires?\s+in\s+\d+|hurry\s+up|only\s+\d+\s+(?:slots|seats|hours|minutes))\b",
        "The offer applies time pressure intended to shorten independent checking.",
    ),
    (
        "offer_unrealistic_claim",
        "suspicious",
        0.60,
        0.45,
        r"\b(?:guaranteed\s+(?:returns?|profit|income|winner|approval)|100\s*%\s+(?:guaranteed|free|profit)|double\s+your\s+(?:money|investment)|risk[- ]free\s+(?:investment|profit)|earn\s+₹?\d+\s*(?:per\s+(?:day|week)|daily)|no\s+questions\s+asked)\b",
        "The offer makes a financial or outcome claim that warrants independent verification.",
    ),
    (
        "offer_personal_channel",
        "unverified",
        0.30,
        0.40,
        r"\b(?:whatsapp|telegram|dm\s+us|direct\s+message|personal\s+email)\b",
        "The offer directs the recipient to an informal or personal communication channel.",
    ),
)

_CATEGORY_PATTERNS: dict[str, tuple[tuple[str, float, str, str], ...]] = {
    "giveaway": (
        (
            "offer_giveaway_pay_to_claim",
            0.70,
            r"\b(?:pay\s+(?:a\s+)?(?:fee|amount|charge)|shipping\s+(?:fee|charge)|claim\s+(?:fee|charge)|processing\s+(?:fee|charge)|to\s+claim\s+(?:your\s+)?(?:prize|reward))\b",
            "A giveaway requires payment before a prize can be claimed.",
        ),
        (
            "offer_giveaway_share_manipulation",
            0.52,
            r"\b(?:share\s+(?:this|to|with)\s+\d*|tag\s+\d+\s+friends|forward\s+to\s+\d+|like\s+and\s+share|repost\s+to\s+win)\b",
            "The giveaway conditions participation on forwarding or tagging other people.",
        ),
    ),
    "scholarship": (
        (
            "offer_scholarship_fee",
            0.66,
            r"\b(?:scholarship\s+(?:processing|application|registration|verification)\s+fee|refundable\s+(?:fee|deposit)|fee\s+to\s+(?:process|release)\s+(?:the\s+)?scholarship)\b",
            "A scholarship announcement requests a fee to process or release the award.",
        ),
    ),
    "investment": (
        (
            "offer_investment_guarantee",
            0.66,
            r"\b(?:guaranteed\s+(?:monthly|weekly|daily|fixed)\s+(?:return|income|profit)|assured\s+returns?|principal\s+(?:is\s+)?safe|zero\s+risk|insured\s+returns?)\b",
            "An investment offer promises guaranteed or risk-free returns.",
        ),
    ),
    "recruitment": (
        (
            "offer_recruitment_fee",
            0.66,
            r"\b(?:no\s+interview|(?:instant|immediate)\s+(?:appointment|joining)|joining\s+(?:fee|allowance)|appointment\s+letter\s+fee)\b",
            "A recruitment offer combines a fee with a bypassed selection process.",
        ),
    ),
    "promotion": (
        (
            "offer_promotion_impersonation",
            0.58,
            r"\b(?:official\s+(?:partner|reseller|representative)\s+of|authorised\s+by\s+(?:the\s+)?(?:company|brand|government)|in\s+association\s+with\s+(?:google|amazon|microsoft|sbi|hdfc|icici|paytm|flipkart))\b",
            "The promotion claims an official relationship that has not been independently verified.",
        ),
    ),
}

_CAVEAT = (
    "This is a text pattern observed in the submitted offer. It is not proof of fraud, "
    "does not identify a business as fraudulent, and must be corroborated with independent "
    "verification before any action is taken."
)


def build_offer_indicators(text: str, category: str = "other") -> list[dict[str, Any]]:
    """Return EvidenceIndicator-shaped observations for generic offer text.

    ``category`` selects additional category-specific patterns but never changes
    the meaning of a generic signal. An unknown category falls back to ``other``.
    """
    content = str(text or "")
    selected = category if category in _CATEGORY_PATTERNS else "other"
    indicators: list[dict[str, Any]] = []

    for name, status, severity, confidence, pattern, explanation in _GENERIC_PATTERNS:
        if re.search(pattern, content, flags=re.IGNORECASE):
            indicators.append(
                make_indicator(
                    name=name,
                    status=status,
                    severity=severity,
                    confidence=confidence,
                    description=f"[{selected}] {explanation} {_CAVEAT}",
                    source="offer_rules",
                )
            )

    for name, severity, pattern, explanation in _CATEGORY_PATTERNS.get(selected, ()):
        if re.search(pattern, content, flags=re.IGNORECASE):
            indicators.append(
                make_indicator(
                    name=name,
                    status="suspicious",
                    severity=severity,
                    confidence=0.48,
                    description=f"[{selected}] {explanation} {_CAVEAT}",
                    source="offer_rules",
                )
            )

    return indicators


__all__ = ["OFFER_CATEGORIES", "build_offer_indicators"]
