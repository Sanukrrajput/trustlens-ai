"""Company intelligence endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user, get_repositories, get_services
from app.core.config import Settings, get_app_settings
from app.db.repositories import Repositories
from app.schemas import CompanyVerifyRequest
from app.utils.serialization import doc_out, json_safe

router = APIRouter(prefix="/company", tags=["company"])


@router.post("/verify")
def verify_company(
    payload: CompanyVerifyRequest,
    settings: Settings = Depends(get_app_settings),
    repos: Repositories = Depends(get_repositories),
    services: dict[str, Any] = Depends(get_services),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    verifier = services["company_verifier"]
    result = verifier.verify(
        payload.company_name,
        website_url=payload.website_url,
        corporate_id=payload.corporate_id,
        consent_external=payload.consent_external_lookups,
        consent_registry=payload.consent_corporate_registry_lookup,
    )
    repos.audit.log(str(user["id"]), "company.verify", target=payload.company_name)
    return json_safe(result) or {}


@router.get("/{company_id}")
def get_company(
    company_id: str,
    repos: Repositories = Depends(get_repositories),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    doc = repos.companies.get(company_id)
    if not doc:
        raise HTTPException(status_code=404, detail="company record not found")
    result = doc_out(doc) or {}
    previous = repos.analyses.find(
        {"extracted.company_fingerprint": doc.get("name_fingerprint")}, limit=20
    )
    result["previous_investigations"] = [
        {
            "id": str(item.get("_id")),
            "created_at": item.get("created_at"),
            "score": (item.get("risk") or {}).get("score"),
            "category": (item.get("risk") or {}).get("category"),
        }
        for item in previous
    ]
    return result
