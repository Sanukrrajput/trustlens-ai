"""Shared query construction helpers."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from pymongo import ASCENDING, DESCENDING

from app.utils import parse_ts, utcnow


def time_filter(
    field: str = "timestamp",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[str, Any]:
    clause: dict[str, Any] = {}
    if date_from:
        clause["$gte"] = parse_ts(date_from)
    if date_to:
        clause["$lte"] = parse_ts(date_to)
    return {field: clause} if clause else {}


def merge(*filters: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for item in filters:
        merged.update(item)
    return merged


def text_filter(query: str | None, fields: list[str]) -> dict[str, Any]:
    if not query:
        return {}
    pattern = query.strip()
    return {"$or": [{field: {"$regex": pattern, "$options": "i"}} for field in fields]}


def sort_spec(sort: str | None, default: str, allowed: set[str], order: str | None = "desc") -> list[tuple[str, int]]:
    field = sort if sort in allowed else default
    direction = DESCENDING if (order or "desc").lower() == "desc" else ASCENDING
    return [(field, direction)]


def paginate_args(page: int, page_size: int) -> tuple[int, int]:
    return max(1, page), min(200, max(1, page_size))


def since_days(days: int) -> datetime:
    return utcnow() - timedelta(days=max(1, min(365, days)))
