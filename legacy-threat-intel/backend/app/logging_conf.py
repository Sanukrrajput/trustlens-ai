"""Structured application logging configuration."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings


class JsonLikeFormatter(logging.Formatter):
    """Compact, parseable single-line records without extra dependencies."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = []
        for key in ("source", "job", "incident_id", "detection_id", "event_id"):
            value = getattr(record, key, None)
            if value is not None:
                extras.append(f"{key}={value}")
        if extras:
            return f"{base} | " + " ".join(extras)
        return base


def configure_logging(settings: "Settings") -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonLikeFormatter(
            "%(asctime)sZ %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("apscheduler").setLevel(max(level, logging.WARNING))
    logging.getLogger("pymongo").setLevel(max(level, logging.WARNING))
