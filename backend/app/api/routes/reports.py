"""Investigation report download, export and feedback endpoints."""

from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user, get_repositories, require_admin
from app.core.security import utcnow
from app.db.repositories import Repositories
from app.schemas import UserReportCreate, UserReportOut
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


# Static paths are registered before the dynamic /{analysis_id} route.
@router.post("/feedback", response_model=UserReportOut)
def submit_feedback(
    payload: UserReportCreate,
    repos: Repositories = Depends(get_repositories),
    user: dict[str, Any] = Depends(get_current_user),
) -> UserReportOut:
    _owned_analysis(payload.analysis_id, repos, user)
    doc = repos.user_reports.insert(
        {
            **payload.model_dump(),
            "user_id": str(user["id"]),
            "status": "pending_review",
            "reviewed_by": None,
            "created_at": utcnow(),
        }
    )
    data = doc_out(doc) or {}
    return UserReportOut(**data)


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
        headers={"Content-Disposition": 'attachment; filename="hireshield-analyses.csv"'},
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
        headers={"Content-Disposition": f'attachment; filename="hireshield-report-{analysis_id}.pdf"'},
    )
