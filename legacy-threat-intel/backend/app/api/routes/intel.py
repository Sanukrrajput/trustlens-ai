"""Threat intelligence, assets, sources, models and settings endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_mongo, get_repos, get_services, get_settings, require_api_key
from app.config import Settings
from app.db.mongo import MongoDBService
from app.db.repositories import Repositories
from app.schemas import AssetInput, IndicatorInput, SettingsUpdate, SourceToggle
from app.utils import json_safe, utcnow

router = APIRouter(prefix="/intel", tags=["intel"], dependencies=[Depends(require_api_key)])


@router.get("/indicators")
def list_indicators(
    page: int = 1,
    page_size: int = 25,
    q: str | None = None,
    kind: str | None = None,
    malicious_only: bool = False,
    repos: Repositories = Depends(get_repos),
) -> dict[str, Any]:
    query: dict[str, Any] = {}
    if kind:
        kinds = [item.strip() for item in kind.split(",") if item.strip()]
        query["type"] = {"$in": kinds} if len(kinds) > 1 else kinds[0]
    if malicious_only:
        query["is_malicious"] = True
    if q:
        query["normalized_value"] = {"$regex": q, "$options": "i"}
    page, page_size = max(1, page), min(200, max(1, page_size))
    return repos.indicators.paginate(query, page=page, page_size=page_size, sort_field="last_seen")


@router.get("/indicators/{indicator_id}")
def get_indicator(indicator_id: str, repos: Repositories = Depends(get_repos)) -> dict[str, Any]:
    indicator = repos.indicators.find_one({"indicator_id": indicator_id})
    if not indicator:
        raise HTTPException(404, "indicator not found")
    return json_safe(indicator)


@router.post("/indicators/enrich")
def enrich_indicator(
    payload: IndicatorInput,
    force: bool = False,
    services: dict[str, Any] = Depends(get_services),
) -> dict[str, Any]:
    result = services["enrichment"].enrich(payload.type, payload.value, force=force)
    if not result.get("valid"):
        raise HTTPException(400, result.get("reason", "invalid indicator"))
    return json_safe(result)


@router.get("/assets")
def list_assets(repos: Repositories = Depends(get_repos)) -> dict[str, Any]:
    assets = repos.assets.find({}, sort_field="criticality", limit=500)
    return {"items": json_safe(assets), "total": len(assets)}


@router.post("/assets")
def create_asset(payload: AssetInput, repos: Repositories = Depends(get_repos)) -> dict[str, Any]:
    asset = payload.model_dump()
    asset.update(created_at=utcnow(), updated_at=utcnow())
    stored = repos.assets.upsert(asset)
    repos.audit.write("asset_upserted", "analyst", {"asset_id": payload.asset_id})
    return json_safe(stored)


@router.patch("/assets/{asset_id}")
def update_asset(
    asset_id: str,
    payload: AssetInput,
    repos: Repositories = Depends(get_repos),
) -> dict[str, Any]:
    if payload.asset_id != asset_id:
        raise HTTPException(400, "asset_id in body must match path")
    return create_asset(payload, repos)


@router.get("/models")
def list_models(services: dict[str, Any] = Depends(get_services)) -> dict[str, Any]:
    models = services["ml"].status()
    return {"items": json_safe(models), "total": len(models)}


@router.post("/models/train")
def train_models(services: dict[str, Any] = Depends(get_services)) -> dict[str, Any]:
    result = services["train"]()
    return json_safe(result)


@router.get("/sources")
def list_sources(services: dict[str, Any] = Depends(get_services)) -> dict[str, Any]:
    sources = services["ingestion"].list_sources()
    return {"items": json_safe(sources), "total": len(sources)}


@router.post("/sources/{name}/collect")
def collect_source(
    name: str,
    services: dict[str, Any] = Depends(get_services),
    repos: Repositories = Depends(get_repos),
) -> dict[str, Any]:
    if not services["ingestion"].source_by_name(name):
        raise HTTPException(404, "source not found")
    result = services["ingestion"].run_source(name)
    repos.audit.write("source_collection_run", "analyst", {"source": name, "success": result.success})
    return json_safe(result.to_doc())


@router.patch("/sources/{name}")
def toggle_source(
    name: str,
    payload: SourceToggle,
    settings: Settings = Depends(get_settings),
    repos: Repositories = Depends(get_repos),
) -> dict[str, Any]:
    if not services_has_source(settings, name):
        raise HTTPException(404, "source not found")
    toggles = dict(repos.settings.get("source_toggles", {}) or {})
    entry = toggles.get(name, {})
    entry.update({"enabled": payload.enabled})
    if payload.authorized is not None:
        entry["authorized"] = payload.authorized
    toggles[name] = entry
    enabled = [s for s in settings.enabled_sources if s != name]
    if payload.enabled:
        enabled.append(name)
    settings.enabled_sources = enabled
    repos.settings.set("source_toggles", toggles, actor="analyst")
    repos.audit.write("source_toggled", "analyst", {"source": name, "enabled": payload.enabled})
    return {"name": name, "enabled": payload.enabled, "authorized": entry.get("authorized", True)}


def services_has_source(settings: Settings, name: str) -> bool:
    known = {"windows_eventlog", "windows_eventlog_file", "application_log", "urlhaus_feed"}
    return name in known


@router.get("/settings")
def get_platform_settings(
    settings: Settings = Depends(get_settings),
    repos: Repositories = Depends(get_repos),
) -> dict[str, Any]:
    return json_safe(
        {
            "environment": settings.public_dict(),
            "runtime_thresholds": repos.settings.get("detection_thresholds", {}),
            "source_toggles": repos.settings.get("source_toggles", {}),
        }
    )


@router.put("/settings")
def update_platform_settings(
    payload: SettingsUpdate,
    repos: Repositories = Depends(get_repos),
) -> dict[str, Any]:
    current = dict(repos.settings.get("detection_thresholds", {}) or {})
    current.update(payload.overrides)
    repos.settings.set("detection_thresholds", current, actor="analyst")
    repos.audit.write("detection_thresholds_updated", "analyst", {"overrides": payload.overrides})
    return {"status": "updated", "thresholds": json_safe(current)}


@router.get("/system/health")
def system_health(
    services: dict[str, Any] = Depends(get_services),
    mongo: MongoDBService = Depends(get_mongo),
) -> dict[str, Any]:
    return json_safe(services["health"].snapshot(services["scheduler"].status()))


@router.get("/jobs")
def list_jobs(repos: Repositories = Depends(get_repos)) -> dict[str, Any]:
    jobs = repos.jobs.find({}, sort_field="started_at", limit=100)
    return {"items": json_safe(jobs), "total": len(jobs)}
