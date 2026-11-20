"""Tests for the optional, safe image/OCR engine."""

from __future__ import annotations

import io
import sys
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.intelligence.image import ocr as ocr_module  # noqa: E402
from app.intelligence.image.ocr import ImageOCR  # noqa: E402
from app.services.analysis_service import DocumentParser  # noqa: E402


def _png(text: str = "") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 32), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_invalid_image_is_rejected_without_pretending_to_read_it():
    result = ImageOCR().extract(b"not-an-image", "image/png")
    assert result["status"] == "invalid_image"
    assert result["text"] == ""
    assert any(item["name"] == "image_ocr_unavailable" for item in result["indicators"])
    assert all(item["status"] != "confirmed_malicious" for item in result["indicators"])


def test_missing_tesseract_reports_not_configured(monkeypatch):
    monkeypatch.setattr(ocr_module, "tesseract_available", lambda: False)
    result = ImageOCR().extract(_png(), "image/png")
    assert result["status"] == "not_configured"
    assert result["image"]["width"] == 64
    assert "no tesseract binary" in " ".join(result["limitations"]).lower()
    assert result["text"] == ""
    assert any(item["status"] == "technical_limitation" for item in result["indicators"])


def test_non_image_mime_is_not_attempted():
    result = ImageOCR().extract(b"text", "text/plain")
    assert result["status"] == "not_attempted"
    assert result["entities"] == {}


def test_extracted_text_yields_labelled_observations_only(monkeypatch):
    monkeypatch.setattr(ocr_module, "tesseract_available", lambda: True)
    monkeypatch.setitem(
        sys.modules,
        "pytesseract",
        SimpleNamespace(
            image_to_string=lambda image, lang, timeout: (
                "Pay the fee to jobs@example.com or visit https://offer.example.com. "
                "Share your OTP. Call +91 98765 43210."
            )
        ),
    )
    result = ImageOCR().extract(_png(), "image/png")
    assert result["status"] == "ok"
    assert result["entities"]["emails"] == ["jobs@example.com"]
    assert result["entities"]["urls"] == ["https://offer.example.com"]
    assert result["entities"]["phone_numbers"]
    names = {item["name"] for item in result["indicators"]}
    assert {"image_contact_details", "image_payment_request", "image_credential_request"}.issubset(names)
    descriptions = " ".join(item["description"] for item in result["indicators"])
    assert "never proves" in descriptions.lower()


def test_document_parser_delegates_image_ocr(monkeypatch):
    monkeypatch.setattr(ocr_module, "tesseract_available", lambda: False)
    text, image_result, limitations = DocumentParser.parse("shot.png", _png(), "image/png")
    assert text == ""
    assert image_result["status"] == "not_configured"
    assert limitations
