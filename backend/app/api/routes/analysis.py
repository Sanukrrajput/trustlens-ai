"""Analysis submission and history endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status

from app.api.deps import enforce_rate_limit, get_current_user, get_repositories, get_services
from app.core.config import Settings, get_app_settings
from app.core.security import validate_upload
from app.db.repositories import Repositories
from app.schemas import (
    AnalysisListItem,
    AnalysisResult,
    DocumentAnalysisRequest,
    JobAnalysisRequest,
    MessageAnalysisRequest,
    Paginated,
    TaskStatusOut,
    UrlAnalysisRequest,
)
from app.services.analysis_service import AnalysisService
from app.utils.serialization import doc_out, json_safe

router = APIRouter(prefix="/analysis", tags=["analysis"])


def _service(
    settings: Settings,
    repos: Repositories,
    services: dict[str, Any],
) -> AnalysisService:
    return AnalysisService(
        settings,
        repos,
        services["notifications"],
        services["plans"],
    )


def _to_result(document: dict[str, Any]) -> AnalysisResult:
    data = doc_out(document) or {}
    return AnalysisResult(**data)


@router.post("/job", response_model=AnalysisResult)
def analyse_job(
    payload: JobAnalysisRequest,
    request: Request,
    settings: Settings = Depends(get_app_settings),
    repos: Repositories = Depends(get_repositories),
    services: dict[str, Any] = Depends(get_services),
    user: dict[str, Any] = Depends(get_current_user),
    _: None = Depends(enforce_rate_limit),
) -> AnalysisResult:
    try:
        result = _service(settings, repos, services).run(
            str(user["id"]),
            "job",
            payload.model_dump(),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    return _to_result(result)


@router.post("/message", response_model=AnalysisResult)
def analyse_message(
    payload: MessageAnalysisRequest,
    settings: Settings = Depends(get_app_settings),
    repos: Repositories = Depends(get_repositories),
    services: dict[str, Any] = Depends(get_services),
    user: dict[str, Any] = Depends(get_current_user),
    _: None = Depends(enforce_rate_limit),
) -> AnalysisResult:
    try:
        result = _service(settings, repos, services).run(
            str(user["id"]),
            "message",
            payload.model_dump(),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    return _to_result(result)


@router.post("/url", response_model=AnalysisResult)
def analyse_url(
    payload: UrlAnalysisRequest,
    settings: Settings = Depends(get_app_settings),
    repos: Repositories = Depends(get_repositories),
    services: dict[str, Any] = Depends(get_services),
    user: dict[str, Any] = Depends(get_current_user),
    _: None = Depends(enforce_rate_limit),
) -> AnalysisResult:
    try:
        result = _service(settings, repos, services).run(
            str(user["id"]),
            "url",
            payload.model_dump(),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    return _to_result(result)


@router.post("/document", response_model=AnalysisResult)
async def analyse_document(
    file: UploadFile = File(...),
    consent_external_lookups: bool = Form(False),
    client_request_id: str | None = Form(None),
    settings: Settings = Depends(get_app_settings),
    repos: Repositories = Depends(get_repositories),
    services: dict[str, Any] = Depends(get_services),
    user: dict[str, Any] = Depends(get_current_user),
    _: None = Depends(enforce_rate_limit),
) -> AnalysisResult:
    content = await file.read()
    declared_mime = file.content_type or "application/octet-stream"
    try:
        _, safe_name = validate_upload(file.filename or "upload", declared_mime, content, settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = DocumentAnalysisRequest(
        consent_external_lookups=consent_external_lookups,
        client_request_id=client_request_id,
    ).model_dump()
    payload.update({"filename": safe_name, "mime": declared_mime, "content": content})
    try:
        result = _service(settings, repos, services).run(str(user["id"]), "document", payload)
    except PermissionError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    return _to_result(result)


@router.get("", response_model=Paginated[AnalysisListItem])
def list_analyses(
    page: int = 1,
    page_size: int = 20,
    analysis_type: str | None = None,
    repos: Repositories = Depends(get_repositories),
    user: dict[str, Any] = Depends(get_current_user),
) -> Paginated[AnalysisListItem]:
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(status_code=400, detail="invalid pagination parameters")
    docs, total = repos.analyses.for_user(
        str(user["id"]), page=page, page_size=page_size, analysis_type=analysis_type
    )
    items = []
    for doc in docs:
        data = doc_out(doc) or {}
        items.append(
            AnalysisListItem(
                id=str(data["id"]),
                analysis_type=data.get("analysis_type", "job"),
                created_at=data["created_at"],
                status=data.get("status", "completed"),
                input_preview=data.get("input_preview", ""),
                risk_score=(data.get("risk") or {}).get("score"),
                risk_category=(data.get("risk") or {}).get("category"),
                company_name=next(iter((data.get("extracted") or {}).get("company_names") or []), None),
            )
        )
    import math

    return Paginated(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, math.ceil(total / page_size)),
    )


@router.get("/{analysis_id}", response_model=AnalysisResult | TaskStatusOut)
def get_analysis(
    analysis_id: str,
    repos: Repositories = Depends(get_repositories),
    user: dict[str, Any] = Depends(get_current_user),
) -> AnalysisResult | TaskStatusOut:
    doc = repos.analyses.get(analysis_id)
    if not doc:
        # Workers may return a task id before an analysis document exists.
        task = repos.tasks.get(analysis_id)
        if task:
            data = json_safe(task) or {}
            return TaskStatusOut(
                task_id=analysis_id,
                status=str(data.get("status", "queued")),
                result=data.get("result"),
                error=data.get("error"),
            )
        raise HTTPException(status_code=404, detail="analysis not found")
    if str(doc.get("user_id")) != str(user["id"]) and user.get("role") not in {"admin", "owner"}:
        raise HTTPException(status_code=404, detail="analysis not found")
    return _to_result(doc)
