"""Source abstraction with explicit authorization and availability gates."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from app.schemas import NormalizedEvent
from app.utils import to_iso, utcnow

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class CollectionResult:
    source: str
    success: bool
    started_at: datetime
    finished_at: datetime
    records_read: int = 0
    records_inserted: int = 0
    duplicates: int = 0
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_doc(self) -> dict[str, Any]:
        data = asdict(self)
        data.update(
            started_at=self.started_at,
            finished_at=self.finished_at,
            duration_ms=round((self.finished_at - self.started_at).total_seconds() * 1000, 2),
        )
        return data


class IngestionSource(ABC):
    """Every collector must declare authorization and availability before reading data."""

    name: str = "base"
    source_type: str = "generic"

    def __init__(self, settings: "Settings"):
        self.settings = settings
        self.logger = logging.getLogger(f"{__name__}.{self.name}")

    def is_authorized(self) -> bool:
        return (
            self.name in {s.strip().lower() for s in self.settings.authorized_sources}
            and self.name in {s.strip().lower() for s in self.settings.enabled_sources}
        )

    @abstractmethod
    def check_available(self) -> tuple[bool, str]:
        """Return (available, human-readable reason). Must not raise."""

    @abstractmethod
    def collect(self, since: datetime | None = None) -> list[NormalizedEvent]:
        """Collect and normalize records. Caller applies retries and deduplication."""

    def status_document(self, *, available: bool | None = None, reason: str = "", error: str = "", **extra: Any) -> dict[str, Any]:
        if available is None:
            available, reason = self.check_available()
        return {
            "name": self.name,
            "source_type": self.source_type,
            "authorized": self.is_authorized(),
            "enabled": self.name in {s.strip().lower() for s in self.settings.enabled_sources},
            "available": bool(available),
            "status": (
                "disabled" if not self.is_authorized() else ("unavailable" if not available else "healthy")
            ),
            "reason": reason or error,
            "last_error": error or None,
            "last_checked_at": utcnow(),
            "last_success_at": utcnow() if available and not error else None,
            "metadata": extra,
        }

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        return to_iso(value)
