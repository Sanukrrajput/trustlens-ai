"""Administrative controls for the optional threat-indicator source registry."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_app_settings, get_repositories, require_admin
from app.core.config import Settings
from app.db.repositories import Repositories
from app.intelligence.threat_indicators import ThreatIndicatorStore
from app.schemas import ThreatImport, ThreatSourceRegister
from app.utils.serialization import doc_out

router = APIRouter(prefix="/threat-intelligence", tags=["threat-intelligence"])


def _store(settings: Settings, repos: Repositories) -> ThreatIndicatorStore:
    return ThreatIndicatorStore(settings, repos)


@router.get("/sources")
def list_sources(
    settings: Settings = Depends(get_app_settings),
    repos: Repositories = Depends(get_repositories),
    admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    repos.audit.log(str(admin["id"]), "threat_source.list")
    return {"sources": _store(settings, repos).sources()}


@router.post("/sources")
def register_source(
    payload: ThreatSourceRegister,
    settings: Settings = Depends(get_app_settings),
    repos: Repositories = Depends(get_repositories),
    admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    try:
        result = _store(settings, repos).register_source(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    repos.audit.log(
        str(admin["id"]),
        "threat_source.register",
        target=str(result.get("source_id") or payload.source_id),
        metadata={"kind": payload.kind, "enabled": payload.enabled},
    )
    return result


@router.post("/sources/{source_id}/refresh")
def refresh_source(
    source_id: str,
    settings: Settings = Depends(get_app_settings),
    repos: Repositories = Depends(get_repositories),
    admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    """Fetch an operator-registered JSON feed through the SSRF-safe fetcher."""
    result = _store(settings, repos).refresh_source(source_id)
    repos.audit.log(
        str(admin["id"]),
        "threat_source.refresh",
        target=source_id,
        metadata={"status": result.get("status"), "ingested": result.get("ingested")},
    )
    return result


@router.post("/import")
def import_indicators(
    payload: ThreatImport,
    settings: Settings = Depends(get_app_settings),
    repos: Repositories = Depends(get_repositories),
    admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    result = _store(settings, repos).ingest([item.model_dump() for item in payload.indicators])
    repos.audit.log(
        str(admin["id"]),
        "threat_indicator.import",
        metadata={"ingested": result.get("ingested"), "skipped": result.get("skipped")},
    )
    return result


@router.get("/indicators")
def list_indicators(
    limit: int = 50,
    settings: Settings = Depends(get_app_settings),
    repos: Repositories = Depends(get_repositories),
    _: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 200")
    rows = [doc_out(item) or {} for item in repos.threat_indicators.find({}, limit=limit)]
    return {"total": repos.threat_indicators.count(), "items": rows}
