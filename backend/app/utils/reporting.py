"""PDF and CSV report generation from stored investigation results."""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _clean(value: Any, limit: int = 400) -> str:
    text = str(value if value is not None else "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = text.replace("\u20b9", "INR ").replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _table(data: list[list[str]], widths: list[float], header: bool = True) -> Table:
    table = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ]
    table.setStyle(TableStyle(style))
    return table


def generate_analysis_pdf(analysis: dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="TrustLens AI Investigation Report",
        author="TrustLens AI",
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=18, textColor=colors.HexColor("#0F172A"))
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12, spaceBefore=10, textColor=colors.HexColor("#0F172A"))
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=9, alignment=TA_LEFT, leading=13)
    small = ParagraphStyle("Small", parent=body, fontSize=7.5, textColor=colors.HexColor("#475569"))

    risk = analysis.get("risk") or {}
    story: list[Any] = [
        Paragraph("TrustLens AI Investigation Report", h1),
        Paragraph(
            f"Report ID: {_clean(analysis.get('id'))} | Generated: {datetime.now(timezone.utc).isoformat()}",
            small,
        ),
        HRFlowable(width="100%", color=colors.HexColor("#0EA5E9"), thickness=1.2, spaceAfter=8),
    ]

    if risk.get("inconclusive"):
        story.append(Paragraph("INCONCLUSIVE: available evidence is insufficient for a confident assurance.", h2))

    story.append(
        _table(
            [
                ["Risk score", "Category", "Confidence", "Data coverage"],
                [
                    f"{risk.get('score', 0)}/100",
                    _clean(risk.get("category")),
                    f"{float(risk.get('confidence', 0)) * 100:.0f}%",
                    f"{float(risk.get('data_coverage', 0)) * 100:.0f}%",
                ],
            ],
            [40 * mm, 55 * mm, 40 * mm, 43 * mm],
        )
    )
    story.append(Spacer(1, 6))
    story.append(Paragraph(_clean(risk.get("summary")), body))

    uncertainty = risk.get("uncertainty")
    if uncertainty is None:
        uncertainty = 1.0 - float(risk.get("confidence", 0.0))
    story.append(
        _table(
            [
                ["Assessment confidence", "Evidence uncertainty", "Unavailable signal categories"],
                [
                    f"{float(risk.get('confidence', 0)) * 100:.0f}%",
                    f"{float(uncertainty) * 100:.0f}%",
                    _clean(", ".join(risk.get("unavailable_signals") or []) or "none", 120),
                ],
            ],
            [45 * mm, 45 * mm, 88 * mm],
        )
    )
    story.append(Spacer(1, 6))

    signal_weights = risk.get("signal_weights") or {}
    component_scores = risk.get("component_scores") or {}
    if signal_weights:
        story.append(Paragraph("Signal categories and weights", h2))
        rows = [["Category", "Weight", "Observed component score"]]
        for name, weight in signal_weights.items():
            rows.append(
                [
                    _clean(name.replace("_", " ").title(), 40),
                    f"{float(weight) * 100:.0f}%",
                    f"{float(component_scores.get(name, 0)) * 100:.0f}%",
                ]
            )
        rows.append(["Weights version", _clean(risk.get("weights_version"), 60), ""])
        story.append(_table(rows, [55 * mm, 35 * mm, 88 * mm]))

    evidence_sources = analysis.get("evidence_sources") or []
    if evidence_sources:
        story.append(Paragraph("Evidence sources and timestamps", h2))
        rows = [["Source", "Status", "Attempted", "Observed", "Detail"]]
        for source in evidence_sources[:20]:
            rows.append(
                [
                    _clean(source.get("name"), 40),
                    _clean(source.get("status"), 30),
                    _clean(source.get("attempted_at"), 30),
                    _clean(source.get("observed_at"), 30),
                    _clean(source.get("detail"), 120),
                ]
            )
        story.append(_table(rows, [32 * mm, 24 * mm, 32 * mm, 32 * mm, 58 * mm]))

    if risk.get("evidence_summary"):
        story.append(Paragraph("Evidence summary", h2))
        for item in risk["evidence_summary"][:12]:
            story.append(Paragraph(f"&bull; {_clean(item)}", body))

    indicators = analysis.get("indicators") or []
    if indicators:
        story.append(Paragraph("Risk indicators and evidence", h2))
        rows = [["Indicator", "Status", "Severity", "Description", "Source"]]
        for ind in indicators[:40]:
            rows.append(
                [
                    _clean(ind.get("name"), 70),
                    _clean(ind.get("status"), 30),
                    f"{float(ind.get('severity', 0)) * 100:.0f}%",
                    _clean(ind.get("description"), 240),
                    _clean(ind.get("source"), 80),
                ]
            )
        story.append(_table(rows, [34 * mm, 25 * mm, 16 * mm, 72 * mm, 31 * mm]))

    extracted = analysis.get("extracted") or {}
    if any(extracted.values()):
        story.append(Paragraph("Extracted information", h2))
        rows = [["Field", "Value"]]
        for key, value in extracted.items():
            if value in (None, [], "", {}):
                continue
            rows.append([_clean(key.replace("_", " ").title()), _clean(value, 300)])
        story.append(_table(rows, [42 * mm, 136 * mm]))

    predictions = analysis.get("model_predictions") or []
    if predictions:
        story.append(Paragraph("Model assessments", h2))
        rows = [["Model", "Version", "Result", "Uncalibrated risk score"]]
        for pred in predictions:
            rows.append(
                [
                    _clean(pred.get("model_name"), 60),
                    _clean(pred.get("model_version"), 30),
                    _clean(pred.get("prediction"), 40),
                    f"{float(pred.get('fraud_probability', 0)) * 100:.1f}%",
                ]
            )
        story.append(_table(rows, [65 * mm, 30 * mm, 40 * mm, 43 * mm]))

    for title, key in [
        ("Domain investigation", "domain_intelligence"),
        ("Company intelligence", "company_intelligence"),
        ("Brand and campaign verification", "brand_intelligence"),
        ("Threat-indicator check", "threat_intelligence"),
        ("Image/OCR analysis", "image_intelligence"),
        ("Message analysis", "message_intelligence"),
        ("Historical patterns", "historical_intelligence"),
    ]:
        section = analysis.get(key) or {}
        if section:
            story.append(Paragraph(title, h2))
            rows = [["Field", "Finding"]]
            for field, value in list(section.items())[:15]:
                if field in {"indicators", "signals", "evidence"} or isinstance(value, (list, dict)):
                    continue
                if value in (None, "", []):
                    continue
                rows.append([_clean(field.replace("_", " ").title()), _clean(value, 300)])
            if len(rows) > 1:
                story.append(_table(rows, [42 * mm, 136 * mm]))

    story.append(Paragraph("Missing information / evidence", h2))
    for item in (analysis.get("missing_evidence") or [])[:12]:
        story.append(Paragraph(f"&bull; {_clean(item)}", body))

    story.append(Paragraph("Technical limitations", h2))
    for item in (analysis.get("technical_limitations") or [])[:12]:
        story.append(Paragraph(f"&bull; {_clean(item)}", body))

    story.append(Paragraph("Recommended next steps", h2))
    for item in (risk.get("recommended_actions") or [])[:12]:
        story.append(Paragraph(f"&bull; {_clean(item)}", body))

    story.append(Spacer(1, 10))
    story.append(
        KeepTogether(
            Paragraph(
                "Important: a low risk score does not prove an offer, advert, recruiter, brand or company is genuine. "
                "This report is an evidence-based screening aid, not a calibrated fraud probability, a legal "
                "determination or an accusation.",
                small,
            )
        )
    )
    doc.build(story)
    return buffer.getvalue()


def generate_csv(rows: list[dict[str, Any]], columns: list[str] | None = None) -> bytes:
    if not rows:
        return b""
    columns = columns or list(rows[0].keys())
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: _clean(row.get(column), 500) for column in columns})
    return output.getvalue().encode("utf-8-sig")
