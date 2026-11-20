"""Safe, optional OCR and screenshot-signal extraction.

OCR is a *local, optional* capability: it uses pytesseract only when a local
tesseract binary is present. When it is not installed the engine reports
``not_configured`` and extracts no text. It never invents image contents, never
claims that a logo or screenshot proves authenticity, and never executes an
uploaded file.
"""

from __future__ import annotations

import io
import re
import shutil
from typing import Any

from PIL import Image, UnidentifiedImageError

from app.intelligence import dedupe, make_indicator

IMAGE_MIMES = frozenset({"image/png", "image/jpeg", "image/webp"})
MAX_IMAGE_PIXELS = 25_000_000

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]{2,}")
_URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_PHONE = re.compile(r"(?:\+?\d{1,3}[\s-]?)?(?:\d[\s-]?){10}")
_PAYMENT = re.compile(
    r"\b(?:pay|payment|fee|deposit|upi|bank account|account number|gpay|phonepe|paytm)\b",
    re.IGNORECASE,
)
_CREDENTIAL = re.compile(r"\b(?:otp|one time password|password|pin|cvv|verification code)\b", re.IGNORECASE)

_CAVEAT = (
    "Text or contact details extracted from an image are observations only. An image, logo or "
    "screenshot never proves that a company, campaign or message is genuine."
)


def tesseract_available() -> bool:
    """True only when a local tesseract executable can be found."""
    return shutil.which("tesseract") is not None


def _entities(text: str) -> dict[str, list[str]]:
    return {
        "emails": dedupe(_EMAIL.findall(text)),
        "urls": dedupe(match.rstrip(".,;)") for match in _URL.findall(text)),
        "phone_numbers": dedupe(re.sub(r"\s+", "", match) for match in _PHONE.findall(text)),
    }


class ImageOCR:
    """Extract text and clearly-labelled signals from an in-memory image."""

    def __init__(self, languages: str = "eng", timeout_seconds: int = 15) -> None:
        self.languages = languages or "eng"
        self.timeout_seconds = timeout_seconds

    def extract(self, content: bytes, mime: str) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": "not_attempted",
            "text": "",
            "image": {},
            "entities": {},
            "indicators": [],
            "limitations": [],
        }
        if mime not in IMAGE_MIMES:
            result["status"] = "not_attempted"
            result["limitations"].append(f"Image OCR was not attempted for MIME type '{mime}'.")
            return result

        try:
            with Image.open(io.BytesIO(content)) as probe:
                probe.verify()
            with Image.open(io.BytesIO(content)) as image:
                width, height = image.size
                if width * height > MAX_IMAGE_PIXELS:
                    raise ValueError("image dimensions exceed the safe processing limit")
                result["image"] = {
                    "width": width,
                    "height": height,
                    "format": str(image.format or ""),
                    "mode": str(image.mode or ""),
                }
                if not tesseract_available():
                    result["status"] = "not_configured"
                    result["limitations"].append(
                        "Local OCR is not configured: no tesseract binary is available. "
                        "No text was extracted from the image; do not treat the image as verified."
                    )
                else:
                    import pytesseract

                    text = pytesseract.image_to_string(
                        image, lang=self.languages, timeout=self.timeout_seconds
                    )
                    result["text"] = str(text or "")[:200_000]
                    result["status"] = "ok" if result["text"].strip() else "no_text_found"
                    if result["status"] == "no_text_found":
                        result["limitations"].append("OCR completed but recognised no text in the image.")
        except (UnidentifiedImageError, ValueError) as exc:
            result["status"] = "invalid_image"
            result["limitations"].append(f"Image validation failed: {type(exc).__name__}")
        except Exception as exc:  # noqa: BLE001 - OCR is optional and must never break analysis
            result["status"] = "error"
            result["limitations"].append(f"Image OCR failed: {type(exc).__name__}")

        entities = _entities(result["text"])
        result["entities"] = entities

        if result["status"] in {"not_configured", "error", "invalid_image", "no_text_found"}:
            result["indicators"].append(
                make_indicator(
                    name="image_ocr_unavailable",
                    status="technical_limitation",
                    severity=0.0,
                    confidence=1.0,
                    description=(
                        f"Image text could not be extracted (status: {result['status']}). "
                        "This is missing evidence, not evidence that the offer is legitimate."
                    ),
                    source="image_ocr",
                )
            )

        if entities["phone_numbers"] or entities["emails"] or entities["urls"]:
            result["indicators"].append(
                make_indicator(
                    name="image_contact_details",
                    status="unverified",
                    severity=0.2,
                    confidence=0.4,
                    description=(
                        "Contact details were extracted from image text. " + _CAVEAT
                    ),
                    source="image_ocr",
                )
            )

        if _PAYMENT.search(result["text"]):
            result["indicators"].append(
                make_indicator(
                    name="image_payment_request",
                    status="unverified",
                    severity=0.5,
                    confidence=0.4,
                    description="The image text mentions a payment or money transfer. " + _CAVEAT,
                    source="image_ocr",
                )
            )

        if _CREDENTIAL.search(result["text"]):
            result["indicators"].append(
                make_indicator(
                    name="image_credential_request",
                    status="suspicious",
                    severity=0.6,
                    confidence=0.45,
                    description="The image text mentions a credential or secret. " + _CAVEAT,
                    source="image_ocr",
                )
            )

        return result


__all__ = ["IMAGE_MIMES", "ImageOCR", "tesseract_available"]
