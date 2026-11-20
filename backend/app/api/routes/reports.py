"""Investigation report download, export and feedback endpoints."""

from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user, get_repositories, require_admin
from app.core.security import utcnow
from app.db.repositories import Repositories
from app.schemas import CommunityReportCreate, UserReportCreate, UserReportOut
from app.services.community_service import submit_report
from app.utils.reporting import generate_analysis_pdf, generate_csv
from app.utils.serialization import doc_out, json_safe

router = APIRouter(prefix="/reports", tags=["reports"])


def _owned_analysis(analysis_id: str, repos: Repositories, user: dict[str, Any]) -> dict[str, Any]:
    doc = repos.analyses.get(analysis_id)
    if not doc:
        raise HTTPException(status_code=404, detail="analysis not found")
    if str(doc.get("user_id")) != str(user["id"]) and user.get("role") not in {"admin", "owner"}:
        raise HTTPException(status_code=403, detail="not permitted")
    return doc


def _report_out(document: dict[str, Any]) -> UserReportOut:
    data = doc_out(document) or {}
    return UserReportOut(**data)


# Static paths are registered before the dynamic /{analysis_id} route.
@router.post("/feedback", response_model=UserReportOut)
def submit_feedback(
    payload: UserReportCreate,
    repos: Repositories = Depends(get_repositories),
    user: dict[str, Any] = Depends(get_current_user),
) -> UserReportOut:
    """Submit a correction to a specific assessment.

    Corrections are stored with ``category='correction'`` and can never become
    community evidence, even if a moderator later takes action on them.
    """

    analysis = _owned_analysis(payload.analysis_id, repos, user)
    document, _duplicate = submit_report(
        repos=repos,
        analysis_doc=analysis,
        user_id=str(user["id"]),
        category="correction",
        report_type=payload.report_type,
        details=payload.details,
        evidence_url=payload.evidence_url,
    )
    return _report_out(document)


@router.post("/community", response_model=UserReportOut)
def submit_community_report(
    payload: CommunityReportCreate,
    repos: Repositories = Depends(get_repositories),
    user: dict[str, Any] = Depends(get_current_user),
) -> UserReportOut:
    """Submit a community allegation about the entity behind an analysis.

    Duplicate submissions by the same reporter return the original report with
    ``duplicate=true``. Reports by different reporters remain distinct so that
    independent corroboration can be counted honestly.
    """

    analysis = _owned_analysis(payload.analysis_id, repos, user)
    document, _duplicate = submit_report(
        repos=repos,
        analysis_doc=analysis,
        user_id=str(user["id"]),
        category="community",
        report_type=payload.claim_type,
        details=payload.details,
        evidence_url=payload.evidence_url,
    )
    return _report_out(document)


@router.get("/export/analyses.csv")
def export_analyses_csv(
    repos: Repositories = Depends(get_repositories),
    admin: dict[str, Any] = Depends(require_admin),
) -> StreamingResponse:
    docs = repos.analyses.find({}, limit=5000)
    rows = []
    for doc in docs:
        risk = doc.get("risk") or {}
        rows.append(
            {
                "analysis_id": str(doc.get("_id")),
                "created_at": doc.get("created_at"),
                "analysis_type": doc.get("analysis_type"),
                "risk_score": risk.get("score"),
                "risk_category": risk.get("category"),
                "inconclusive": risk.get("inconclusive"),
                "indicator_count": len(doc.get("indicators") or []),
            }
        )
    content = generate_csv(rows, ["analysis_id", "created_at", "analysis_type", "risk_score", "risk_category", "inconclusive", "indicator_count"])
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="trustlens-analyses.csv"'},
    )


@router.get("/{analysis_id}")
def get_report(analysis_id: str, repos: Repositories = Depends(get_repositories), user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    doc = _owned_analysis(analysis_id, repos, user)
    report = repos.reports.for_analysis(analysis_id) or {}
    return {
        "analysis_id": analysis_id,
        "report_id": str(report.get("_id")) if report else None,
        "generated_at": report.get("generated_at"),
        "risk": doc.get("risk"),
        "status": "available",
    }


@router.get("/{analysis_id}/pdf")
def download_pdf(analysis_id: str, repos: Repositories = Depends(get_repositories), user: dict[str, Any] = Depends(get_current_user)) -> Response:
    doc = _owned_analysis(analysis_id, repos, user)
    report = repos.reports.for_analysis(analysis_id)
    if report and report.get("pdf_base64"):
        pdf_bytes = base64.b64decode(report["pdf_base64"])
    else:
        pdf_bytes = generate_analysis_pdf(json_safe(doc) or {})
        repos.reports.upsert(
            analysis_id,
            {
                "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
                "generated_at": utcnow(),
                "bytes": len(pdf_bytes),
            },
        )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="trustlens-report-{analysis_id}.pdf"'},
    )
