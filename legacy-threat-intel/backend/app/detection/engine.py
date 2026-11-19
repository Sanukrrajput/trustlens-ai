"""Detection pipeline: rules + optional ML -> explainable risk -> persisted detections."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from app.detection.features import build_feature_vectors
from app.detection.ml import MLDetector
from app.detection.rules import RuleEngine
from app.risk.scoring import RiskScorer
from app.utils import make_id, utcnow

if TYPE_CHECKING:
    from app.config import Settings
    from app.db.repositories import Repositories

logger = logging.getLogger(__name__)


class DetectionEngine:
    def __init__(self, settings: "Settings", repos: "Repositories", ml: MLDetector):
        self.settings = settings
        self.repos = repos
        self.ml = ml

    def _overrides(self) -> dict[str, Any]:
        return self.repos.settings.get("detection_thresholds", {}) or {}

    def process(self, events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if events is None:
            events = self.repos.events.find_unprocessed(limit=500)
        if not events:
            return {"events_processed": 0, "detections_produced": 0, "new_detections": 0, "ml_status": self._ml_status()}

        indicators_map = self.repos.indicators.malicious_map()
        thresholds = self._overrides()
        rule_candidates = RuleEngine(self.settings, thresholds).evaluate(events, indicators_map)
        vectors = build_feature_vectors(
            events,
            indicators_map,
            business_start=int(thresholds.get("rule_unusual_hours_start", self.settings.rule_unusual_hours_start)),
            business_end=int(thresholds.get("rule_unusual_hours_end", self.settings.rule_unusual_hours_end)),
        )
        ml_candidates = self.ml.score(vectors, indicators_map)
        candidates = rule_candidates + ml_candidates

        risk_overrides = {
            k: v for k, v in thresholds.items() if k.startswith("risk_weight_")
        }
        scorer = RiskScorer(self.settings, risk_overrides)
        existing_keys = {
            doc.get("detection_key")
            for doc in self.repos.detections.find({}, sort_field="created_at", limit=5000)
            if doc.get("detection_key")
        }
        persisted: list[dict[str, Any]] = []
        for candidate in candidates:
            assessment = scorer.score(candidate)
            document = {
                "detection_id": make_id("det", candidate["detection_key"]),
                "detection_key": candidate["detection_key"],
                "type": candidate["type"],
                "rule_id": candidate.get("rule_id"),
                "model_id": candidate.get("model_version"),
                "title": candidate["title"],
                "description": "; ".join(assessment["detection_reasons"])[:1500],
                "severity": assessment["severity"],
                "risk_score": assessment["risk_score"],
                "confidence": assessment["confidence"],
                "uncertainty": assessment["uncertainty"],
                "calibrated_probability": False,
                "scoring_version": assessment["scoring_version"],
                "rule_version": candidate.get("rule_version"),
                "model_version": candidate.get("model_version"),
                "contributing_signals": assessment["contributing_signals"],
                "detection_reasons": assessment["detection_reasons"],
                "raw_signals": candidate.get("signals", {}),
                "event_ids": candidate.get("event_ids", []),
                "indicator_ids": candidate.get("indicator_ids", []),
                "entity_key": candidate.get("entity_key", ""),
                "source_ip": candidate.get("source_ip"),
                "actor_user": candidate.get("actor_user"),
                "asset_ids": candidate.get("asset_ids", []),
                "status": "new",
                "created_at": utcnow(),
                "last_seen": utcnow(),
                "window_start": candidate.get("window_start"),
                "expires_at": utcnow() + timedelta(days=self.settings.detection_retention_days),
            }
            stored = self.repos.detections.upsert(document)
            persisted.append(stored)
        self.repos.events.mark_processed([str(event["event_id"]) for event in events])
        new_count = sum(1 for doc in persisted if doc.get("detection_key") not in existing_keys)
        logger.info(
            "detection run events=%s candidates=%s new=%s",
            len(events),
            len(candidates),
            new_count,
        )
        return {
            "events_processed": len(events),
            "detections_produced": len(persisted),
            "new_detections": new_count,
            "ml_status": self._ml_status(),
            "detection_types": {"rule": len(rule_candidates), "ml": len(ml_candidates)},
        }

    def _ml_status(self) -> str:
        active = [doc for doc in self.ml.status() if doc.get("name") in {"isolation_forest", "random_forest"}]
        if not active or all(doc.get("status") == "untrained" for doc in active):
            return "untrained - rule-based detection only"
        return "trained"
