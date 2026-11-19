"""Conversion helpers for MongoDB documents and API responses."""

from __future__ import annotations

from bson import ObjectId
from datetime import date, datetime

from app.db.repositories import public


def json_safe(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items() if key != "_id"}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return value


def doc_out(document: dict | None) -> dict | None:
    return json_safe(public(document))
