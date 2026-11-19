"""Explainable, configurable 0-100 risk scoring (not a calibrated probability)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.config import Settings

SCORING_VERSION = "1.0.0"


def severity_for(score: float) -> str:
    if score >= 85:
        return "critical"
    if score >= 65:
        return "high"
    if score >= 40:
        return "medium"
    if score >= 20:
        return "low"
    return "informational"


class RiskScorer:
    def __init__(self, settings: "Settings", overrides: dict[str, Any] | None = None):
        self.settings = settings
        self.overrides = overrides or {}

    def _weight(self, name: str, attribute: str) -> float:
        key = f"risk_weight_{name}"
        return float(self.overrides.get(key, getattr(self.settings, attribute)))

    def score(self, candidate: dict[str, Any]) -> dict[str, Any]:
        weights = {
            "threat_intelligence": self._weight("ti", "risk_weight_ti"),
            "ml_anomaly": self._weight("ml", "risk_weight_ml"),
            "rule_severity": self._weight("rule", "risk_weight_rule"),
            "asset_criticality": self._weight("asset", "risk_weight_asset"),
            "correlation": self._weight("correlation", "risk_weight_correlation"),
        }
        total_weight = sum(max(0.0, value) for value in weights.values()) or 1.0
        weights = {name: max(0.0, value) / total_weight for name, value in weights.items()}

        ti = min(1.0, max(0.0, float(candidate.get("ti_confidence") or 0))) * 100
        signals = candidate.get("signals") or {}
        anomaly = float(
            signals.get("anomaly_score")
            or signals.get("malicious_class_score", 0) * 100
            or candidate.get("base_score", 0)
        )
        anomaly = min(100.0, max(0.0, anomaly))
        rule_severity = float(candidate.get("base_score") or 0)
        asset = min(100.0, max(0.0, float(candidate.get("asset_criticality") or 0) / 5.0 * 100.0))
        correlation = min(100.0, max(0.0, float(candidate.get("correlation_evidence") or 0) * 100.0))

        values = {
            "threat_intelligence": ti,
            "ml_anomaly": anomaly,
            "rule_severity": rule_severity,
            "asset_criticality": asset,
            "correlation": correlation,
        }
        contributions = [
            {
                "signal": name,
                "raw_value": round(values[name], 2),
                "weight": round(weights[name], 3),
                "points": round(values[name] * weights[name], 2),
            }
            for name in values
        ]
        risk_score = round(sum(item["points"] for item in contributions), 2)
        reasons = list(candidate.get("reasons") or [])
        present = sum(1 for value in values.values() if value > 0)
        confidence = min(0.99, max(0.1, float(candidate.get("confidence") or 0.5) * (0.6 + 0.1 * present)))
        return {
            "risk_score": risk_score,
            "severity": severity_for(risk_score),
            "contributing_signals": contributions,
            "detection_reasons": reasons,
            "scoring_version": SCORING_VERSION,
            "rule_version": candidate.get("rule_version"),
            "model_version": candidate.get("model_version"),
            "confidence": round(confidence, 3),
            "uncertainty": round(1.0 - confidence, 3),
            "calibrated_probability": False,
            "interpretation": "Relative risk ranking derived from weighted evidence; not a probability.",
            "event_references": candidate.get("event_ids", []),
        }
